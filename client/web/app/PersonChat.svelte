<script>
  // Переписка с человеком: лента писем и строка отправки.
  //
  // Живёт в его карточке: письма читают, глядя на того, кому пишут.

  import { tick as painted } from 'svelte';

  import ChatBubble from '$components/ChatBubble.svelte';
  import { attempts } from '$state/attempts.js';
  import { byDays, sendBlock, unread } from '$state/chat.js';
  import { appended, nearTop } from '$state/paging.js';

  let { ask, say, card, events, onread } = $props();

  let messages = $state([]);
  let hasMore = $state(false);
  let loaded = $state(false);
  let digging = $state(false);
  let draft = $state('');
  let sending = $state(false);
  let attaching = $state(false);
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
    await toUnread();
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
   *
   * Дочитанное встаёт над показанным и сдвигает ленту вниз на свою высоту.
   * Прокрутку двигаем на столько же: без поправки человек, долиставший до
   * начала разговора, оказывался бы посреди только что подгруженного — а теперь
   * страницы тянет сама прокрутка, и было бы это на каждой.
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
    const was = feed === null ? 0 : feed.scrollHeight;
    messages = appended(page.messages, messages);
    hasMore = page.has_more;
    await painted();
    if (feed !== null) feed.scrollTop += feed.scrollHeight - was;
  }

  /** Дочитать старое, когда лента подошла к началу разговора.
   *
   * Прокруткой, а не нажатием: переписку листают вверх глазами, и строка-ссылка
   * посреди чтения заставляет целиться в неё мышью.
   */
  function scrolled(event) {
    if (!hasMore || digging || !nearTop(event.currentTarget)) return;
    older();
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

  /** Приложить файл к переписке.
   *
   * Файл называет диалог самого окна, а не страница: браузер отдаёт выбранное
   * содержимым, а боту нужен путь. Закрытый диалог ничего не отправляет и
   * отказом не считается — про него мост говорит отдельным словом.
   */
  async function attach() {
    if (attaching) return;
    // Признак свой, не отправки письма: диалог выбора висит, пока человек ищет
    // файл, — минуты, — и общий признак всё это время говорил бы, что письмо
    // летит, и запирал бы кнопку отправки.
    attaching = true;
    const done = await ask('hr.pick_media', card.hr_id);
    attaching = false;
    if (done === null || !alive || done.cancelled) return;
    say('Файл отправлен');
    return refresh();
  }

  /** Открыть вложение тем, чем его открывает система.
   *
   * Открывает не страница, а мост: в ленте адрес ведёт на раздачу окна, а
   * системе нужен путь на диске — и не всякий: имя файла называет собеседник.
   * Своим зовом, не тем, которым открывают ссылки: заслоны у них разные.
   * Отказ показывает плашкой сам зов.
   */
  function open(message) {
    return ask('system.open_attachment', message.media_path);
  }

  /** Показать то, ради чего переписку открыли: первое непрочитанное письмо, а
   *  если всё прочитано — конец ленты.
   *
   * Ждём отрисовки: до неё у ленты прежняя высота, и прокрутка встала бы на
   * предпоследнее письмо.
   */
  async function toUnread() {
    await painted();
    if (!feed) return;
    const first = feed.querySelector('[data-unread="true"]');
    if (first === null) feed.scrollTop = feed.scrollHeight;
    else feed.scrollTop = first.offsetTop - feed.offsetTop;
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

<div class="cnt-chat-section">
  <div class="cnt-chat-body" bind:this={feed} onscroll={scrolled}>
    {#if !loaded}
      <div class="cnt-chat-empty">Загрузка переписки…</div>
    {:else if !messages.length}
      <div class="cnt-chat-empty">Переписки пока нет.</div>
    {:else}
      {#if digging}
        <div class="cnt-chat-older">Загрузка…</div>
      {:else if hasMore}
        <button class="cnt-chat-older" type="button" onclick={older}>Загрузить старее</button>
      {/if}
      {#each days as one (one.key)}
        <div class="cnt-chat-day">{one.day}</div>
        {#each one.messages as message (message.id)}
          <ChatBubble {message} onopen={open} />
        {/each}
      {/each}
    {/if}
  </div>

  <!-- Строка отправки остаётся на месте и при заслоне, только запертой: пропав,
       она не сказала бы, почему писать нельзя. -->
  <div class="cnt-chat-input-area">
    <button
      class="cnt-chat-attach"
      type="button"
      title="Прикрепить файл"
      disabled={attaching || sending || !!blocked}
      onclick={attach}
    >
      <span class="material-symbols-outlined">attach_file</span>
    </button>

    <textarea
      class="cnt-chat-input"
      rows="1"
      placeholder={sending ? 'Отправка…' : 'Сообщение…'}
      disabled={sending || !!blocked}
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

    <button
      class="cnt-chat-send"
      type="button"
      title="Отправить (Enter)"
      disabled={sending || !!blocked || !draft.trim()}
      onclick={send}
    >
      <span class="material-symbols-outlined">send</span>
    </button>
  </div>

  {#if blocked}
    <div class="cnt-chat-disabled-hint">{blocked}</div>
  {/if}
</div>
