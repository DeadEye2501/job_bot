<script>
  // Окно подтверждения отправки: что уйдёт работодателю — правится здесь.
  //
  // Пункт по виду: текст и письмо — многострочным полем (у письма подписи нет),
  // список и переключатель — строкой с вариантом, галочка — галочкой. Ошибка
  // сайта у поля, отвергнутого при прошлой отправке, стоит под ним.
  //
  // Закрытие окна — «Свернуть»: ожидание не кончается, оно уходит в плашку
  // нижней полосы, а правки остаются.
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
                checked={item.value === 'true'}
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

    <div class="modal-footer">
      <button class="btn" type="button" onclick={() => onfold()}>Свернуть</button>
      <button class="btn" type="button" onclick={() => ondrop()}>Закончить</button>
      <button
        class="btn primary"
        type="button"
        disabled={Boolean(blocked)}
        title={blocked || null}
        onclick={() => onconfirm()}>Подтвердить</button
      >
    </div>
  {/snippet}
</ModalShell>
