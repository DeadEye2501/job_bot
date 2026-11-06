<script>
  // Строка опасной зоны «Удалить текущий профиль» и её подтверждение.
  //
  // Перечень читается на входе в настройки и после удаления: имя текущего
  // профиля стоит в вопросе, а их число запирает кнопку — профиль меняют и
  // переименовывают на другой вкладке, пока эта закрыта.
  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import { living } from '$state/alive.js';
  import { RUNNING } from '$state/progress.js';
  import { round } from '$state/round.svelte.js';
  import { removalLock } from '$state/workspaces.js';

  let { ask, say } = $props();

  let items = $state(null);
  let asking = $state(false);
  // Заперта до ответа: второе нажатие удалило бы профиль, ставший текущим
  // после первого.
  let busy = $state(false);

  const lock = $derived(items === null ? '' : removalLock(items, round.running));
  const current = $derived(items?.find((one) => one.active).name);

  const alive = living();

  async function read() {
    const listed = await ask('workspaces.list');
    if (listed !== null && alive.now) items = listed.items;
  }

  async function remove() {
    asking = false;
    busy = true;
    const done = await ask('workspaces.remove');
    busy = false;
    if (done !== null) say('Профиль удалён');
    if (alive.now) await read();
  }

  $effect(() => alive.entered(read));
</script>

{#if items !== null}
  <div class="danger-row">
    <div>
      <div class="danger-text">Удалить текущий профиль</div>
      <div class="danger-sub">
        Безвозвратно удаляет анкету профиля, его вакансии со всем, что от них, тумблеры
        каналов и сайтов и выбор резюме. Переписка и сам файл резюме остаются.
      </div>
    </div>
    <button
      class="btn danger"
      type="button"
      disabled={!!lock || busy}
      title={lock || null}
      onclick={() => (asking = true)}
    >
      <span class="material-symbols-outlined">person_remove</span>
      Удалить профиль
    </button>
  </div>
{/if}

{#if asking}
  <ConfirmDialog
    message={`Удалить профиль «${current}»?\n\nБудут стёрты его анкета, копия фото, вакансии с откликами и историей, тумблеры каналов и сайтов и выбор резюме. Переписка и файл резюме останутся. Текущим станет первый профиль в списке. Откатить нельзя.`}
    confirmLabel="Удалить профиль"
    locked={round.running ? RUNNING : ''}
    onconfirm={remove}
    oncancel={() => (asking = false)}
  />
{/if}
