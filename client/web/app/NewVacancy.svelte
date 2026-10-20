<script>
  // Заведение вакансии руками: кнопка над списком вакансий и окно заведения.
  //
  // Своим файлом, а не частью экрана списка: у окна своя жизнь — черновик,
  // переживающий уход из раздела, ожидание итога разбора, подборщики компании
  // и человека, — и с поиском, порядком и страницами списка его роднит только
  // то, что после заведения список перечитывают.

  import { untrack } from 'svelte';

  import NewCardDialog from '$components/NewCardDialog.svelte';
  import { awaited } from '$state/awaited.svelte.js';
  import { companyTitle } from '$state/companies.js';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { personName } from '$state/people.js';
  import { labels, sameName } from '$state/picker.js';
  import { round } from '$state/round.svelte.js';
  import { handsOverToggle, isText, pasteLock, vacancyFields, viaBot } from '$state/vacancies.js';

  // `newVacancy` — черновик и положение «Отклик при создании»; держит их
  // оболочка, потому что оба переживают этот экран. `onhandmade(news)` — что
  // сделать с итогом заведения, когда он придёт вестью: им тоже распоряжается
  // оболочка — к его приходу экрана может не быть. `onvacancy(id)` — уйти к
  // вакансии, `onfiled()` — перечитать список.
  let { ask, say, lockedTip, newVacancy, onhandmade, onvacancy, onfiled } = $props();

  // Метка вестей ручного заведения: одна на все вкладки, её же ставит мост.
  const HAND_MADE_ACTION = 'create_from_text';

  const handsOver = $derived(handsOverToggle(newVacancy.handsOver, lockedTip));

  // Заведение руками. Обвязка та же, что у людей и компаний: черновик,
  // заслон пустого названия, гашение окна только по удаче. Черновик держит
  // оболочка, и пока ждут итога, закрытое окно его не стирает.
  const newCard = contactAdding({
    list: {
      // Повтор у полей — переход на существующую: строки не прибавилось.
      again: (answer) => (answer.created === false ? onvacancy(answer.created_id) : onfiled()),
    },
    form: NEW_CARD.vacancy,
    save: (draft) => filed(draft),
    say: (text) => say(text),
    // Держатель берётся один раз: он один на всю жизнь оболочки, и следить
    // за ним как за меняющимся параметром незачем.
    held: untrack(() => newVacancy),
    keeps: () => newVacancy.handed,
  });

  /** Отправить черновик слотом его вкладки.
   *
   * Итог текста и полей с откликом приходит вестью, и ждать её начинают до
   * зова: мгновенный отказ приезжает вестью раньше ответа. Отказ зова снимает
   * ожидание — вести за ним не будет. Имена слотов стоят литералами на самом
   * шве: спрятанные в таблицу, они выпали бы из-под сторожа договора страницы.
   */
  async function filed(draft) {
    const awaits = viaBot(draft, handsOver.checked);
    if (awaits) {
      newVacancy.handed = true;
      awaited.start(HAND_MADE_ACTION, onhandmade);
    }
    const answer = await (isText(draft)
      ? ask('vacancies.create_from_text', {
          raw_text: draft.raw_text,
          posted_at: draft.posted_at,
          hands_over: handsOver.checked,
        })
      : ask('vacancies.create', { ...vacancyFields(draft), hands_over: handsOver.checked }));
    if (answer === null && awaits) {
      newVacancy.handed = false;
      awaited.cancel(HAND_MADE_ACTION);
    }
    return answer;
  }

  /** Запомнить положение галочки; ответ зову — «легло», держать нечего. */
  function remember(next) {
    newVacancy.handsOver = next;
    return true;
  }

  // Кого предложить компанией и HR-ом в форме заведения. Спрашиваются при
  // открытии окна, а не вместе с экраном: список вакансий их не показывает, а
  // карточек в базе бывают сотни — заезжай они с каждым чтением списка,
  // человек платил бы за них на каждый набранный в поиске знак.
  let linkOptions = $state({ companies: [], hrs: [] });

  // Чем стороны формы отличаются друг от друга: парой полей черновика — номером
  // для моста и именем для поля — и тем, кто умеет назвать запись. Больше
  // ничем, и написанные двумя телами, они разошлись бы молча.
  //
  // Имени слота моста здесь нет нарочно: оно пишется литералом на самом шве
  // (`makeSide` ниже), а спрятанное в таблицу выпадает из-под сторожей
  // договора страницы и молча переживает переименование.
  const SIDES = {
    companies: { id: 'company_id', name: 'company_name', named: (row) => companyTitle(row).name },
    hrs: { id: 'hr_id', name: 'hr_name', named: personName },
  };

  // Полю с подсказкой уезжают подписи: номер карточки человеку не о чем
  // сравнивать с тем, что он набрал, а тёзок различает ник в подписи.
  const suggestions = $derived({
    companies: labels(linkOptions.companies, SIDES.companies.named),
    hrs: labels(linkOptions.hrs, SIDES.hrs.named),
  });

  /** Открыть окно заведения и спросить перечни для его подборщиков.
   *
   * Окно открывается сразу, не дожидаясь перечней: набирать название человек
   * начинает раньше, чем доедут сотни карточек, а подборщики до ответа стоят
   * пустыми и говорят об этом сами.
   */
  async function openNew() {
    newCard.adding = true;
    const now = await ask('vacancies.create_options');
    if (now === null) return;
    linkOptions = now;
  }

  /** Принять набранное в поле стороны: знакомую узнать, незнакомую завести.
   *
   * Заводится сразу, без второго вопроса: вакансию заводят по объявлению, и
   * той компании в базе обычно ещё нет — отправь форма человека заводить её на
   * соседний экран, он вернулся бы к пустому черновику.
   *
   * Имя остаётся в поле и при неудаче: набранное человеком не стирается
   * ответом моста, а о беде он уже прочёл плашкой.
   */
  async function settle(side, typed) {
    const { id, name, named } = SIDES[side];
    // Черновик запоминается свой: пока летит заведение, окно могли закрыть, и
    // тогда на его месте стоит уже чистый — номер, положенный в него, достался
    // бы следующей вакансии.
    const mine = newCard.draft;
    mine[name] = typed;
    // Связь снимается сразу: набрано другое имя, и прежний номер до нового
    // подтверждения не значит ничего. Останься он — отказ моста оставил бы
    // вакансию привязанной к той карточке, которую человек уже сменил.
    mine[id] = null;
    if (!typed) return;
    const known = sameName(linkOptions[side], typed, named);
    if (known !== null) {
      mine[id] = known.id;
      return;
    }
    const made = await makeSide(side, typed);
    if (made === null || newCard.draft !== mine) return;
    mine[id] = made.created_id;
    linkOptions = {
      ...linkOptions,
      [side]: [...linkOptions[side], { id: made.created_id, name: typed }],
    };
  }

  /** Завести незнакомую сторону и назвать её номер.
   *
   * Зовы моста написаны литералами обеими ветками: имя метода должно быть
   * видно на шве, а собранное из кусков там не видно вовсе — ни человеку, ни
   * сторожам договора страницы.
   */
  function makeSide(side, name) {
    return side === 'companies'
      ? ask('companies.create', { name })
      : ask('hr.create', { name });
  }
</script>

<button
  class="icon-btn"
  type="button"
  title="Добавить вакансию"
  onclick={() => openNew()}
>
  <span class="material-symbols-outlined">{NEW_CARD.vacancy.icon}</span>
</button>

{#if newCard.adding}
  <NewCardDialog
    kind="vacancy"
    draft={newCard.draft}
    busy={newCard.saving || awaited.pending(HAND_MADE_ACTION)}
    ready={newCard.ready}
    locked={pasteLock(newCard.draft, handsOver.checked, { running: round.running, lockedTip })}
    options={suggestions}
    toggle={handsOver}
    ontoggle={remember}
    oncompany={(typed) => settle('companies', typed)}
    onhr={(typed) => settle('hrs', typed)}
    onconfirm={() => newCard.create()}
    oncancel={() => (newCard.adding = false)}
  />
{/if}
