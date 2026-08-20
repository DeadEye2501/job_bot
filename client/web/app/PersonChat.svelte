<script>
  // Переписка с человеком: лента писем и строка отправки.
  //
  // Живёт в его карточке: письма читают, глядя на того, кому пишут.
  //
  // Из карточки берутся поля, а не она сама: её перечитывают на каждую правку
  // поля, и целиком она перезаводила бы подписки и ленту — с потерей
  // дочитанного и прыжком в конец.

  import { tick as painted, untrack } from 'svelte';

  import ChatBubble from '$components/ChatBubble.svelte';
  import { living } from '$state/alive.js';
  import { attempts } from '$state/attempts.js';
  import { byDays, unread } from '$state/chat.js';
  import { appended, nearTop } from '$state/paging.js';

  let { ask, say, hrId, blocked, events, onread } = $props();

  let messages = $state([]);
  let hasMore = $state(false);
  let loaded = $state(false);
  let digging = $state(false);
  let draft = $state('');
  let sending = $state(false);
  let attaching = $state(false);
  let feed = $state(null);

  const tries = attempts();
  const alive = living();

  const days = $derived(byDays(messages, new Date()));

  /** Прочитать хвост переписки — полсотни последних писем.
   *
   * Свой счёт попыток: хвост перечитывается и по вести о новом письме, и после
   * отправки, и ответы возвращаются вразнобой — лёгший поверх свежего старый
   * показал бы ленту без только что отправленного.
   */
  async function refresh() {
    const mine = tries.next();
    const page = await ask('hr.messages', { hr_id: hrId });
    if (page === null || !alive.now || tries.stale(mine)) return;
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
      hr_id: hrId,
      before_id: oldest.id,
      before_sent_at: oldest.sent_at,
    });
    digging = false;
    if (page === null || !alive.now) return;
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
    const done = await ask('hr.mark_read', hrId);
    if (done === null || !alive.now) return;
    // Молчим, когда отмечать было нечего: бот в положении «Off» до Telegram не
    // дотягивается и отмечает ноль писем. Скажи мы и об этом, карточка
    // перечиталась бы, лента следом, письма остались бы непрочитанными — и
    // круг пошёл бы заново, без конца.
    if (!done.updated) return;
    // Числа непрочитанного стоят и в карточке, и в строке списка: пересчитать
    // их может только тот, кто их читал.
    onread();
  }

  async function send() {
    const text = draft.trim();
    if (!text || sending || blocked) return;
    sending = true;
    const done = await ask('hr.send_message', { hr_id: hrId, text });
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
    const done = await ask('hr.pick_media', hrId);
    attaching = false;
    if (done === null || !alive.now || done.cancelled) return;
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
    const settled = alive.mounted();
    // Письма приходят и уходят, пока карточка открыта: без подписок человек
    // читал бы снимок той минуты, когда её открыл. Вторая весть — про чужую
    // отметку прочтения, от неё зависит вторая галочка на своих письмах.
    const deafNew = events.on('contacts_hr_messages_arrived', (about) => {
      if (Number(about.hr_id) === hrId) refresh();
    });
    const deafRead = events.on('contacts_hr_read_receipt', (about) => {
      if (Number(about.hr_id) === hrId) refresh();
    });
    // Первое чтение — вне слежения. Довод сюда приходит полем чужой карточки
    // (`hrId={card.hr_id}`), и читается это поле здесь: свёрткой в производное
    // Svelte такое не заворачивает, зависимостью встаёт сама карточка. Читай мы
    // его под слежением — эффект заводился бы заново на каждую её правку, лента
    // схлопывалась бы до последних полусотни писем и прыгала в конец.
    //
    // Смена человека этим не теряется: пока карточка перечитывается с нуля, её
    // разметка показывает «Загрузка…», переписки на экране нет вовсе, и эффект
    // заводится заново вместе с ней.
    untrack(() => refresh());
    return () => {
      settled();
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
