<script>
  // Окно заведения по адресу: одно поле, пояснение под ним и две кнопки.
  //
  // Так заводят канал (по нику или ссылке), агрегатор (по адресу сайта) и
  // контакт вакансии: слова у них свои и лежат обвязкой формы по роду
  // (`state/new_card.js`), а устройство одно.
  //
  // Своим окном, а не общим спрашивающим: у этого есть шапка с крестиком, свой
  // подвал и строка отказа внутри — ошибку в набранном объясняют там же, где
  // его набирали, а не общей плашкой поверх окна.
  import { pressKey } from '$state/keys.js';
  import { NEW_CARD } from '$state/new_card.js';
  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { kind, value, trouble, saving, ready, oninput, onadd, onclose } = $props();

  const form = $derived(NEW_CARD[kind]);
</script>

<ModalShell extra="narrow address-dialog" {onclose}>
  {#snippet children()}
    <ModalHead icon="add_circle" title={form.title} {onclose} />

    <div class="modal-body">
      <!-- Курсор ставится в поле сразу: окно об одном поле и открывают затем,
           чтобы в него набрать. Проверка a11y гасится нарочно — она о формах,
           где полей несколько и выбор первого за человеком. -->
      <!-- svelte-ignore a11y_autofocus -->
      <input
        class="input cnt-input"
        autofocus
        maxlength="200"
        placeholder={form.placeholder}
        {value}
        oninput={(event) => oninput(event.currentTarget.value)}
        onkeydown={(event) => pressKey(event) && onadd()}
      />
      <div class="address-hint">{form.hint}</div>
      {#if trouble}
        <div class="modal-error">{trouble}</div>
      {/if}
    </div>

    <ModalFoot
      label="Добавить"
      busyLabel="Добавляю…"
      busy={saving}
      {ready}
      oncancel={onclose}
      onconfirm={onadd}
    />
  {/snippet}
</ModalShell>
