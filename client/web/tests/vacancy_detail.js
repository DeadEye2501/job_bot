// Карточка вакансии, какой её отдаёт мост: заполнено только то, что видно на
// экране.
//
// Общая на все живые проверки карточки: набор полей у неё длинный, и вторая
// такая же заготовка разошлась бы с первой на первом же новом поле моста.

/** Карточка вакансии от моста; названное в `extra` перебивает заготовку. */
export function vacancyDetail(id, extra = {}) {
  return {
    id,
    status: 'New',
    title: `Вакансия ${id}`,
    description: null,
    score: null,
    score_threshold: 5,
    stack: [],
    history: [],
    events: [],
    hr: null,
    company_id: null,
    company_name: null,
    notes: '',
    raw_text: '',
    source_url: null,
    channel_username: null,
    posted_at: null,
    created_at: null,
    grade: null,
    salary: null,
    salary_min: null,
    salary_max: null,
    salary_currency: null,
    remote: null,
    location: null,
    ...extra,
  };
}
