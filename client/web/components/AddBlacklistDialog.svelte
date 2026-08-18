<script>
  // Окно заведения строки отсева: род, значение с подсказчиком и причина.
  //
  // Подсказчик — подсказка, а не закрытый набор: рядом с ним значение набирают
  // руками, чтобы завести ник, которого в базе ещё нет. Появится такой человек
  // или канал — попадёт под уже заведённую строку сразу.
  import { closeOnClickAway } from '$state/outside.js';
  import ModalKeys from './ModalKeys.svelte';

  let { draft, hints, kinds, saving, onkind, onvalue, onreason, onadd, onclose } = $props();

  let open = $state(false);
  let root = $state(null);

  function pick(value) {
    open = false;
    onvalue(value);
  }

  $effect(() => {
    if (!open) return;
    // Нажатие мимо закрывает подсказчик, а не окно: окно закрывают крестиком и
    // Escape, и падать оно от промаха по списку не должно.
    return closeOnClickAway(() => root, () => (open = false));
  });
</script>

<ModalKeys close={onclose} />

<div class="modal-backdrop" role="presentation">
  <div class="modal-dialog bl-add-modal" role="dialog" aria-modal="true">
    <div class="modal-head">
      <span class="material-symbols-outlined">block</span>
      <div class="modal-title">Добавить в blacklist</div>
      <button class="modal-close" type="button" title="Закрыть" onclick={() => onclose()}>
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>

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

      {#if hints === null}
        <!-- svelte-ignore a11y_autofocus -->
        <input
          class="bl-modal-input"
          autofocus
          maxlength="500"
          autocomplete="off"
          placeholder={draft.placeholder}
          value={draft.value}
          oninput={(event) => onvalue(event.currentTarget.value)}
          onkeydown={(event) => event.key === 'Enter' && onadd()}
        />
      {:else}
        <div class="bl-combobox-wrap" bind:this={root}>
          <!-- svelte-ignore a11y_autofocus -->
          <input
            class="bl-modal-input"
            autofocus
            maxlength="500"
            autocomplete="off"
            placeholder={draft.placeholder}
            value={draft.value}
            onfocus={() => (open = true)}
            oninput={(event) => {
              open = true;
              onvalue(event.currentTarget.value);
            }}
            onkeydown={(event) => event.key === 'Enter' && onadd()}
          />
          {#if open}
            <div class="bl-combobox-dropdown">
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
      {/if}

      <textarea
        class="bl-modal-textarea"
        rows="3"
        maxlength="500"
        placeholder="Причина (опционально)"
        value={draft.reason}
        oninput={(event) => onreason(event.currentTarget.value)}
      ></textarea>
    </div>

    <div class="modal-footer">
      <button class="btn" type="button" onclick={() => onclose()}>Отмена</button>
      <button
        class="btn primary"
        type="button"
        disabled={saving || !draft.value.trim()}
        onclick={() => onadd()}
      >
        {saving ? 'Добавляю…' : 'Добавить'}
      </button>
    </div>
  </div>
</div>
