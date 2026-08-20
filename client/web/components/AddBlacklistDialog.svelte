<script>
  // Окно заведения строки отсева: род, значение с подсказчиком и причина.
  //
  // Подсказчик — подсказка, а не закрытый набор: рядом с ним значение набирают
  // руками, чтобы завести ник, которого в базе ещё нет. Появится такой человек
  // или канал — попадёт под уже заведённую строку сразу.
  import { whileOpen } from '$state/outside.js';

  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { draft, hints, kinds, saving, onkind, onvalue, onreason, onadd, onclose } = $props();

  let open = $state(false);
  let root = $state(null);

  function pick(value) {
    open = false;
    onvalue(value);
  }

  $effect(() => {
    // Нажатие мимо закрывает подсказчик, а не окно: окно закрывают крестиком и
    // Escape, и падать оно от промаха по списку не должно.
    return whileOpen(open, () => root, () => (open = false));
  });
</script>

<ModalShell extra="narrow bl-add-modal" {onclose}>
  {#snippet children()}
    <ModalHead icon="block" title="Добавить в blacklist" {onclose} />

    <div class="modal-body">
      <div class="bl-kind-segmented">
        {#each kinds as kind (kind)}
          <button
            class="bl-kind-seg {kind}"
            class:active={draft.kind === kind}
            type="button"
            onclick={() => {
              open = false;
              onkind(kind);
            }}
          >
            {kind}
          </button>
        {/each}
      </div>

      <!-- Поле одно на оба рода: у слова подсказчика нет вовсе, и второе
           написание того же поля разошлось бы с первым первой же правкой длины.
           Обёртка стоит всегда — она держит выпадающий список у поля. -->
      <div class="bl-combobox-wrap" bind:this={root}>
        <!-- Курсор ставится в поле сразу: окно открывают затем, чтобы в него
             набрать. Проверка a11y гасится нарочно — она о формах, где полей
             несколько и выбор первого за человеком. -->
        <!-- svelte-ignore a11y_autofocus -->
        <input
          class="input bl-modal-input"
          autofocus
          maxlength="500"
          autocomplete="off"
          placeholder={draft.placeholder}
          value={draft.value}
          onfocus={() => (open = hints !== null)}
          oninput={(event) => {
            open = hints !== null;
            onvalue(event.currentTarget.value);
          }}
          onkeydown={(event) => event.key === 'Enter' && onadd()}
        />
        {#if hints !== null && open}
          <div class="pop-frame drop-panel bl-combobox-dropdown">
            {#if hints.empty}
              <div class="bl-combobox-empty">{hints.empty}</div>
            {:else}
              {#each hints.options as one (one.value)}
                <button class="bl-combobox-option" type="button" onclick={() => pick(one.value)}>
                  <span class="opt-label">{one.label}</span>
                  {#if one.sub}<span class="opt-sub">{one.sub}</span>{/if}
                </button>
              {/each}
            {/if}
          </div>
        {/if}
      </div>

      <textarea
        class="input bl-modal-textarea"
        rows="3"
        maxlength="500"
        placeholder="Причина (опционально)"
        value={draft.reason}
        oninput={(event) => onreason(event.currentTarget.value)}
      ></textarea>
    </div>

    <ModalFoot
      label="Добавить"
      busyLabel="Добавляю…"
      busy={saving}
      ready={Boolean(draft.value.trim())}
      oncancel={onclose}
      onconfirm={onadd}
    />
  {/snippet}
</ModalShell>
