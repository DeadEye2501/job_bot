// Куда ведут связи карточки вакансии: наружу — в Telegram и на сайт компании,
// внутрь — в карточки контактов.
//
// Чистые функции: карточка приходит доводом, наружу уходят адреса и отметки
// «куда идти». Ни моста, ни разметки этот файл не знает.

import { siteHref } from './companies.js';

/** Пять связей карточки: две наружу, две внутрь и одна в подборщик.
 *
 * Пустая связь названа пустотой, а не пропущена: карточка ставит на её место
 * неподвижную подпись, и разбирать, чего в ответе нет, ей было бы нечем.
 *
 * Имя компании без привязки ведёт не в контакты, а в подборщик с этим самым
 * именем: связи нет, но разбор её узнал — человек нажимает и сразу видит
 * совпадения, вместо того чтобы набирать то же слово руками.
 */
export function cardLinks(card) {
  const hr = card.hr;
  const linked = card.company_id !== null && card.company_id !== undefined;
  return {
    hrChat: hr?.telegram_username ? `https://t.me/${hr.telegram_username}` : null,
    // Ключи вкладок те же, какими их знает раздел контактов (`sections.js`):
    // по ним он и выбирает, какую открыть.
    hrCard: hr?.id === null || hr?.id === undefined ? null : { tab: 'people', id: hr.id },
    companyCard: linked ? { tab: 'companies', id: card.company_id } : null,
    companyPick: !linked && card.company_name ? card.company_name : null,
    site: siteHref(card.company_website),
  };
}
