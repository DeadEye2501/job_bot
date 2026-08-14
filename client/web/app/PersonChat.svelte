<script>
  // Переписка с человеком: лента писем и строка отправки.
  //
  // Живёт в его карточке: письма читают, глядя на того, кому пишут.

  import { tick as painted } from 'svelte';

  import ChatBubble from '$components/ChatBubble.svelte';
  import { attempts } from '$state/attempts.js';
  import { byDays, sendBlock, unread } from '$state/chat.js';
  import { appended } from '$state/paging.js';

  let { ask, say, card, events, onread } = $props();

  let messages = $state([]);
  let hasMore = $state(false);
  let loaded = $state(false);
  let digging = $state(false);
  let draft = $state('');
  let sending = $state(false);
  let feed = $state(null);

  const tries = attempts();
  let alive = true;

  const days = $derived(byDays(messages, new Date()));
  const blocked = $derived(sendBlock(card));

  /** Прочитать хвост переписки — полсотни последних писем.
   *
   * Свой счёт попыток: хвост перечитывается и по вести о новом письме, и после
   * отправки, и ответы возвращаются вразнобой — лёгший поверх свежего старый
   * показал бы ленту без только что отправленного.
   */
  async function refresh() {
    const mine = tries.next();
    const page = await ask('hr.messages', { hr_id: card.hr_id });
    if (page === null || !alive || tries.stale(mine)) return;
    messages = page.messages;
    hasMore = page.has_more;
    loaded = true;
    await toBottom();
    return markRead();
  }

  /** Дочитать полсотни писем постарше показанных.
   *
   * Опорой идёт самое старое показанное: мост отдаёт письма страницами от него
   * назад, и без опоры вторая страница повторила бы первую.
   *
   * Второе нажатие, пока летит первое, отбивается признаком: опора до ответа не
   * меняется, обе просьбы вернули бы одну страницу, и в ленте оказались бы два
   * письма с одним номером.
   */
  async function older() {
    const oldest = messages[0];
    if (!oldest || digging) return;
    digging = true;
    const page = await ask('hr.messages', {
      hr_id: card.hr_id,
      mode: 'older',
      before_id: oldest.id,
      before_sent_at: oldest.sent_at,
    });
    digging = false;
    if (page === null || !alive) return;
    messages = appended(page.messages, messages);
    hasMore = page.has_more;
  }

  /** Сказать мосту, что письма прочитаны.
   *
   * Смотрим в саму ленту, а не в число из карточки: карточка прочитана один раз
   * при открытии, и пришедшее следом письмо она не считает — отметка не ушла бы
   * в Telegram никогда.
   */
  async function markRead() {
    if (!unread(messages)) return;
    const done = await ask('hr.mark_read', card.hr_id);
    if (done === null || !alive) return;
    // Числа непрочитанного стоят и в карточке, и в строке списка: пересчитать
    // их может только тот, кто их читал.
    onread();
  }

  async function send() {
    const text = draft.trim();
    if (!text || sending || blocked) return;
    sending = true;
    const done = await ask('hr.send_message', { hr_id: card.hr_id, text });
    sending = false;
    // Набранное остаётся при отказе: письмо не ушло, и переписывать его заново
    // человек не должен.
    if (done === null) return;
    draft = '';
    say('Отправлено');
    return refresh();
  }

  /** Показать конец ленты: свежие письма внизу, и читают их оттуда.
   *
   * Ждём отрисовки: до неё у ленты прежняя высота, и прокрутка встала бы на
   * предпоследнее письмо.
   */
  async function toBottom() {
    await painted();
    if (feed) feed.scrollTop = feed.scrollHeight;
  }

  $effect(() => {
    alive = true;
    // Письма приходят и уходят, пока карточка открыта: без подписок человек
    // читал бы снимок той минуты, когда её открыл. Вторая весть — про чужую
    // отметку прочтения, от неё зависит вторая галочка на своих письмах.
    const deafNew = events.on('contacts_hr_messages_arrived', (about) => {
      if (Number(about.hr_id) === card.hr_id) refresh();
    });
    const deafRead = events.on('contacts_hr_read_receipt', (about) => {
      if (Number(about.hr_id) === card.hr_id) refresh();
    });
    refresh();
    return () => {
      alive = false;
      deafNew();
      deafRead();
    };
  });
</script>

<div class="chat" bind:this={feed}>
  {#if !loaded}
    <div class="empty-note">Загрузка переписки…</div>
  {:else if !messages.length}
    <div class="empty-note">Переписки пока нет</div>
  {:else}
    {#if hasMore}
      <button class="add-more" type="button" disabled={digging} onclick={older}>
        {digging ? 'Читаю…' : 'Показать письма постарее'}
      </button>
    {/if}
    {#each days as one (one.key)}
      <div class="chat-day">{one.day}</div>
      {#each one.messages as message (message.id)}
        <ChatBubble {message} />
      {/each}
    {/each}
  {/if}
</div>

{#if blocked}
  <div class="empty-note">{blocked}</div>
{:else}
  <div class="chat-send">
    <!-- Поле не запирается на время отправки: человек набирает следующее письмо,
         пока летит прошлое, и запертое поле выбросило бы каретку. Заперта одна
         кнопка — второе нажатие отправило бы то же письмо дважды. -->
    <textarea
      class="textarea"
      rows="1"
      placeholder="Написать сообщение"
      bind:value={draft}
      onkeydown={(event) => {
        // Enter отправляет, Shift+Enter переносит строку — так же, как в самом
        // Telegram. Набор иероглифа и кириллицы в редакторе ввода тоже кончается
        // Enter'ом, и отправлять на нём нельзя: письмо ушло бы недописанным.
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          send();
        }
      }}
    ></textarea>
    <button class="btn primary" type="button" disabled={sending || !draft.trim()} onclick={send}>
      <span class="material-symbols-outlined">{sending ? 'hourglass_empty' : 'send'}</span>
    </button>
  </div>
{/if}
