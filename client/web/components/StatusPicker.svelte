<script>
  // Смена статуса: чем он станет и почему.
  //
  // Причина необязательна: половина переходов очевидна из переписки, и
  // требовать слов к каждому значило бы получать их пустыми.
  //
  // Столбец радиокнопок, а не ряд чипов: статусов одиннадцать, читают их по
  // порядку — от «New» к «Not Fit», — и в переносящемся ряду этот порядок
  // теряется.
  import { untrack } from 'svelte';

  import { closeOnClickAway } from '$state/outside.js';
  import { saveKey } from '$state/keys.js';

  import ModalKeys from './ModalKeys.svelte';
  import { STATUS_CHOICES } from '$state/statuses.js';

  let { status, saving, wrap, onapply, oncancel } = $props();

  let chosen = $state(untrack(() => status));
  let note = $state('');

  function key(event) {
    if (saveKey(event)) return onapply(chosen, note);
  }

  $effect(() => {
    // Своим узлом, а не по имени класса: окошек на карточке два, и «мимо» у
    // каждого своё. Узел здесь обёртка, а не сама панель, — почему именно так,
    // сказано у сторожа.
    return closeOnClickAway(() => wrap, oncancel);
  });
</script>

<!-- Заперты на время записи обе кнопки внизу: пока ответ в пути, отмена
     оставила бы человека думать, что перехода не было, — а он уже уехал.

     Escape при этом ловится на всё окно, а не в одном поле: окошко открывают
     нажатием по пилюле, и фокус в этот миг стоит на ней, а не в причине. -->
<ModalKeys close={oncancel} />

<div class="pop status-picker">
  <div class="status-options">
    {#each STATUS_CHOICES as one (one.value)}
      <label class="status-option">
        <input
          type="radio"
          name="status-draft"
          value={one.value}
          checked={chosen === one.value}
          onchange={() => (chosen = one.value)}
        />
        <span class="status-dot" data-status={one.value}></span>
        <span>{one.label}</span>
      </label>
    {/each}
  </div>

  <textarea
    class="input popover-comment"
    placeholder="Причина (опционально)..."
    bind:value={note}
    onkeydown={key}
  ></textarea>

  <div class="popover-actions">
    <button class="btn" type="button" disabled={saving} onclick={oncancel}>Отмена</button>
    <button
      class="btn primary"
      type="button"
      disabled={saving}
      onclick={() => onapply(chosen, note)}
    >
      {saving ? 'Сохраняю…' : 'Применить'}
    </button>
  </div>
</div>
