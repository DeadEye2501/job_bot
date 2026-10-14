<script>
  // Окно подтверждения отправки: что уйдёт работодателю — правится здесь.
  //
  // Список и переключатель — строкой, а не своим списком вариантов: варианты
  // знает страница, а не окно, и вариант, ближайший к тексту, выбирает агент.
  //
  // Закрытие окна — «Свернуть»: ожидание не кончается, оно уходит в плашку
  // нижней полосы, а правки остаются.
  import { isChecked } from '$state/round.svelte.js';

  import ModalFoot from './ModalFoot.svelte';
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  // `blocked` — почему «Подтвердить» сейчас заперта, пусто — открыта.
  let { url, items, blocked = '', onedit, onopen, onconfirm, ondrop, onfold } = $props();
</script>

<ModalShell extra="narrow roomy confirm-send" onclose={onfold}>
  {#snippet children()}
    <ModalHead icon="fact_check" title="Проверьте, что уйдёт работодателю" />

    <div class="modal-body">
      {#if url}
        <button class="confirm-send-link link-hover" type="button" onclick={() => onopen(url)}>{url}</button>
      {/if}
      {#each items as item, at (at)}
        <div class="confirm-item">
          {#if item.kind === 'check'}
            <label class="checkbox-row">
              <input
                type="checkbox"
                checked={isChecked(item)}
                onchange={(event) => onedit(at, event.currentTarget.checked ? 'true' : 'false')}
              />
              {item.label}{#if item.required}<span class="confirm-item-required">*</span>{/if}
            </label>
          {:else}
            {#if item.label}
              <div class="field-caption confirm-item-label">
                {item.label}{#if item.required}<span class="confirm-item-required">*</span>{/if}
              </div>
            {/if}
            {#if item.kind === 'choice'}
              <input
                class="input"
                class:missing={item.error}
                value={item.value}
                oninput={(event) => onedit(at, event.currentTarget.value)}
              />
            {:else}
              <textarea
                class="textarea"
                class:missing={item.error}
                rows={item.label ? 2 : 8}
                value={item.value}
                oninput={(event) => onedit(at, event.currentTarget.value)}
              ></textarea>
            {/if}
          {/if}
          {#if item.error}<div class="modal-error">{item.error}</div>{/if}
        </div>
      {/each}
    </div>

    {#snippet fold()}
      <button class="btn" type="button" onclick={() => onfold()}>Свернуть</button>
    {/snippet}
    <ModalFoot
      leading={fold}
      cancelLabel="Закончить"
      label="Подтвердить"
      ready={!blocked}
      tip={blocked}
      oncancel={ondrop}
      {onconfirm}
    />
  {/snippet}
</ModalShell>
