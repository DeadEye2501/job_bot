<script>
  // Кнопка «Профили» в шапке анкеты и её окна: сменить активный профиль или
  // завести новый.
  //
  // Перечень читается при каждом открытии, а не держится: профиль меняют и
  // заводят только отсюда, но должность — имя профиля — правят на этой же
  // вкладке, и перечень, прочитанный раньше, показал бы прежнее имя.
  import ChooseDialog from '$components/ChooseDialog.svelte';
  import { living } from '$state/alive.js';
  import { RUNNING } from '$state/progress.js';
  import { round } from '$state/round.svelte.js';
  import { CREATE_WAYS, workspaceChoices } from '$state/workspaces.js';

  let { ask, onswitched } = $props();

  // Строки открытого окна профилей; пусто — окно закрыто.
  let rows = $state(null);
  // Открыто ли окно способов заведения. Встаёт вместо окна профилей, а не
  // поверх: два окна разом спрашивали бы о двух разных выборах.
  let creating = $state(false);

  const locked = $derived(round.running ? RUNNING : '');

  const alive = living();

  async function open() {
    const listed = await ask('workspaces.list');
    if (listed !== null && alive.now) rows = workspaceChoices(listed.items);
  }

  function create() {
    rows = null;
    creating = true;
  }

  /** Сделать дело моста и перечитать анкету.
   *
   * Анкета перечитывается и после отказа: мост отказывает и тогда, когда
   * профиль уже сменён, а сорвалось что-то после, — и анкета показывала бы
   * прежний профиль.
   */
  async function changed(asking) {
    rows = null;
    creating = false;
    await asking;
    if (alive.now) onswitched();
  }

  $effect(() => alive.mounted());
</script>

<button class="icon-btn workspace-btn" type="button" title="Профили" onclick={open}>
  <span class="material-symbols-outlined">switch_account</span>
</button>

{#if rows !== null}
  <ChooseDialog
    icon="switch_account"
    title="Профили"
    {rows}
    mark="текущий"
    {locked}
    instant
    addLabel="+ Создать новый профиль"
    onadd={create}
    onapply={(row) => changed(ask('workspaces.switch', row.key))}
    onclose={() => (rows = null)}
  />
{/if}

{#if creating}
  <ChooseDialog
    icon="person_add"
    title="Новый профиль"
    rows={CREATE_WAYS}
    {locked}
    instant
    slim
    onapply={(row) => changed(ask('workspaces.create', row.key))}
    onclose={() => (creating = false)}
  />
{/if}
