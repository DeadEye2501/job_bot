<script>
  // Вкладка источника вакансий — каналов или агрегаторов: список слева,
  // карточка выбранного справа, поиск, заведение и общий выключатель сверху.
  //
  // Одной сборкой на оба рода: смотрят на них одинаково, а различия приходят
  // доводами — слова, чтение и правка, строка и карточка фрагментами, открыть
  // ли заведённый (`openCreated`) и перечитывать ли по концу прогона
  // (`rereadOnRound`: у агрегатора вход, время обхода и счёт вакансий меняются
  // тогда). Карточке фрагмент отдаёт и место для ссылки на неё: по ней панель
  // дочитывает вакансии карточки при прокрутке.
  //
  // `source.save` зовёт мост напрямую, а не общей обёрткой: та показывает
  // отказ плашкой и отдаёт пустоту, и слова моста гасли бы в углу, пока
  // человек смотрит в поле.
  import AddressDialog from '$components/AddressDialog.svelte';
  import ContactsPanes from '$components/ContactsPanes.svelte';
  import RowToggle from '$components/RowToggle.svelte';
  import { living } from '$state/alive.js';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { watchContacts } from '$state/contacts_watch.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { takeOpened } from '$state/open_mark.js';
  import { detailScrolled } from '$state/paging.js';
  import { round } from '$state/round.svelte.js';
  import { sourceList } from '$state/source_list.svelte.js';
  import { masterToggle } from '$state/sources.js';

  let {
    kind,
    words,
    source,
    openCreated = null,
    rereadOnRound = false,
    say,
    events,
    open,
    onopened,
    row,
    pane,
  } = $props();

  let opened = $state(null);
  let card = $state(null);

  // Источники приходят разом, без страниц: их десятки, а не тысячи.
  const list = sourceList({
    alive: living(),
    key: source.key,
    read: source.read,
    setActive: source.setActive,
    setAll: source.setAll,
  });

  const master = $derived(masterToggle(list.enabled, words.master));

  // Какой источник открыть, придя со стороны — из статистики.
  $effect(() => takeOpened(open, (id) => (opened = id), onopened));

  const adding = contactAdding({
    list: {
      again: (done) => {
        const id = openCreated?.(done);
        if (id != null) opened = id;
        return list.again();
      },
    },
    form: NEW_CARD[kind],
    save: source.save,
    say: (text) => say(text),
  });

  // Списки меняет не только этот экран: бот заносит источники в отсев сам.
  $effect(() => watchContacts(events, list));
  $effect(() => (rereadOnRound ? round.onFinish(list.again) : undefined));
  // Потерянные вести — конец прогона в их числе — заменяет перечитывание.
  $effect(() => (rereadOnRound ? events.on('missed', list.again) : undefined));

  const shown = {
    get list() {
      return list;
    },
    get opened() {
      return opened;
    },
    close: () => (opened = null),
    getCard: () => card,
    setCard: (one) => (card = one),
  };
</script>

<ContactsPanes
  loaded={list.loaded}
  empty={list.rows.length === 0}
  chosen={opened !== null}
  search={list.search}
  searchHint={words.search}
  addTitle={words.add}
  none={words.none}
  detailEmpty={words.pick}
  onsearch={list.find}
  onadd={() => (adding.adding = true)}
  ondetailscroll={(event) => detailScrolled(event, card)}
>
  {#snippet tools()}
    <!-- Общий выключатель поверх строк: выключенный, гасит обход всех
         источников рода, но положения строк хранит. -->
    <RowToggle checked={master.checked} title={master.title} ontoggle={list.toggleAll} />
  {/snippet}

  {#snippet items()}
    {#each list.rows as item (item.id)}
      {@render row(item, {
        enabled: list.enabled,
        selected: opened === item.id,
        pick: () => (opened = item.id),
        toggle: (on) => list.toggle(item, on),
      })}
    {/each}
  {/snippet}

  {#snippet detail()}
    {@render pane(shown)}
  {/snippet}
</ContactsPanes>

{#if adding.adding}
  <AddressDialog
    {kind}
    value={adding.draft}
    trouble={adding.trouble}
    saving={adding.saving}
    ready={adding.ready}
    oninput={(text) => (adding.draft = text)}
    onadd={() => adding.create()}
    onclose={() => (adding.adding = false)}
  />
{/if}
