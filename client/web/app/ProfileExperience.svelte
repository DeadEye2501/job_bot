<script>
  // Вкладка «Experience»: места работы карточками.
  //
  // Перечень уезжает на мост целиком и заменяет прежний — как и навыки.

  import ConfirmDialog from '$components/ConfirmDialog.svelte';
  import ExperienceCard from '$components/ExperienceCard.svelte';
  import { living } from '$state/alive.js';
  import { toggled, without } from '$state/chosen.js';
  import { experienceReady } from '$state/experience.js';
  import { oneWrite } from '$state/one_write.js';
  import { plural } from '$state/words.js';

  let { ask } = $props();

  let leaving = $state(null);
  let trouble = $state('');

  let loaded = $state(false);
  let rows = $state([]);
  // Навыки анкеты: мост шлёт их вместе с опытом именно для стека — связать
  // место работы он умеет только с заведённым навыком. Держим строки целиком:
  // подборщик раскладывает их по категориям и показывает уровень.
  let known = $state([]);
  let open = $state(new Set());

  const alive = living();
  // Свежим карточкам номера даёт мост, и до первой записи их нет. Свой ключ
  // нужен до тех пор: по нему список узнаёт строку, а раскрытость помнится
  // набором ключей — держи мы там сами записи, любая правка подменяла бы
  // объект, и карточка складывалась бы на каждом введённом символе.
  let born = 0;

  async function refresh() {
    const now = await ask('profile.experience');
    if (now === null || !alive.now) return;
    rows = now.experience.map((one) => ({ ...one, key: `id-${one.id}` }));
    known = now.skills_index;
    loaded = true;
  }

  const write = oneWrite((going) => ask('profile.save_experience', { experience: going }));

  /** Отправить перечень целиком.
   *
   * Отсеиваются только свежие недозаполненные карточки: они ещё не в базе, и
   * пропустить их значит ничего не потерять — а без отсева одна пустая
   * карточка отменяла бы правки всех соседних, заполненных.
   *
   * Уже записанная карточка не отсеивается никогда, чем бы её ни опустошили:
   * мост заменяет перечень целиком, и вычеркнутая из посылки была бы стёрта из
   * базы молча. Про такую говорим сами и не отправляем ничего — так номер в
   * жалобе считается по тому списку, который человек видит, а не по укороченной
   * посылке.
   *
   * Свой ключ на мост не уезжает: он про показ, не про запись.
   */
  function save() {
    const going = rows.filter((one) => one.id !== null || experienceReady(one));
    const at = going.findIndex((one) => !experienceReady(one));
    if (at !== -1) {
      trouble = `Место работы #${rows.indexOf(going[at]) + 1}: заполните компанию, должность и дату начала — пока они пусты, перечень не записывается.`;
      return Promise.resolve();
    }
    trouble = '';
    return write(going.map(({ key, ...one }) => one));
  }

  function edit(key, part) {
    rows = rows.map((one) => (one.key === key ? { ...one, ...part } : one));
    return save();
  }

  function remove(key) {
    // Окно подтверждения гасится здесь, а не нажатием: держится оно на самой
    // уносимой записи, и не сбрось её — окно осталось бы висеть поверх списка,
    // спрашивая про место работы, которого в нём уже нет.
    leaving = null;
    rows = rows.filter((one) => one.key !== key);
    open = without(open, key);
    return save();
  }

  function add() {
    born += 1;
    const fresh = {
      key: `new-${born}`,
      id: null,
      company: '',
      company_url: '',
      role: '',
      start_date: null,
      end_date: null,
      achievements: [],
      responsibilities: [],
      skill_names: [],
    };
    // Первой в списке: места работы идут от свежего к давнему, и добавляют
    // почти всегда последнее — внизу человек искал бы его глазами.
    rows = [fresh, ...rows];
    // Свежая карточка раскрыта сразу: свёрнутая пустая выглядит как пустая
    // строка списка, и человек жал бы «добавить» второй раз.
    open = toggled(open, fresh.key);
  }

  $effect(() => {
    const settled = alive.mounted();
    refresh();
    return () => {
      settled();
    };
  });
</script>

{#if !loaded}
  <div class="empty-note">Загрузка…</div>
{:else}
  <div class="page-head">
    <div class="page-title">
      Профиль / Experience
      <span class="page-title-meta">
        {rows.length}
        {plural(rows.length, 'место', 'места', 'мест')} работы
      </span>
    </div>
  </div>

  {#each rows as exp (exp.key)}
    <ExperienceCard
      {exp}
      {known}
      open={open.has(exp.key)}
      ontoggle={() => (open = toggled(open, exp.key))}
      onedit={(part) => edit(exp.key, part)}
      onremove={() => (leaving = exp)}
    />
  {/each}

  <button class="new-exp" type="button" onclick={add}>+ Добавить место работы</button>

  {#if trouble}
    <div class="autosave-error">{trouble}</div>
  {/if}
{/if}

{#if leaving}
  <ConfirmDialog
    message={`Удалить место работы «${leaving.company || 'без названия'}»?`}
    confirmLabel="Удалить"
    onconfirm={() => remove(leaving.key)}
    oncancel={() => (leaving = null)}
  />
{/if}
