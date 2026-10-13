// Кнопка по подписи — найти или нажать.
//
// Ищется по всей странице, а не внутри смонтированного куска: окна встают
// поверх экрана, а не в нём. Подпись берётся вхождением, а с `exact` — целиком:
// «Создать» вхождением нашлось бы и в «Создать вакансию». `among` сужает поиск
// до своего рода кнопок — пунктов меню, например, — чтобы чужая кнопка с тем же
// словом не подменила искомую.

/** Кнопка с этой подписью. */
export function buttonBy(label, { exact = false, among = 'button' } = {}) {
  return [...document.querySelectorAll(among)].find((one) =>
    exact ? one.textContent.trim() === label : one.textContent.includes(label),
  );
}

/** Набрать в поле, как это делает человек: значение и всплывающая весть ввода. */
export function typed(field, text) {
  field.value = text;
  field.dispatchEvent(new Event('input', { bubbles: true }));
}

/** Нажать кнопку с этой подписью. */
export function press(label, options) {
  buttonBy(label, options).click();
}
