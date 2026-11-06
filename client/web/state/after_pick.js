// Выбор файла диалогом окна: что делать, когда диалог ответил.

/** Дождаться выбора файла и сделать следующее.
 *
 * Закрытый диалог, отказ моста и ушедший экран не меняют ничего: человек
 * передумал, беду уже назвала плашка, а мёртвому экрану некуда показывать.
 */
export async function afterPick(picking, alive, next) {
  const answer = await picking;
  if (answer === null || !alive.now || answer.cancelled) return;
  await next(answer);
}
