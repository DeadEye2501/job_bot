<script>
  // Контакты вакансии в её карточке: список, окно добавления и удаление.
  //
  // Своей сборкой, а не кусками карточки: у контактов свой мост и своё окно, а
  // карточка и без них велика. Список после правки приходит в ответе моста и
  // уходит карточке целиком — перечитывать её ради одной строки незачем.

  import { call } from '$api/bridge.js';
  import AddressDialog from '$components/AddressDialog.svelte';
  import VacancyContacts from '$components/VacancyContacts.svelte';
  import { contactAdding } from '$state/contact_adding.svelte.js';
  import { NEW_CARD } from '$state/new_card.js';
  import { contactHref } from '$state/vacancy_contacts.js';

  let { vacancyId, contacts, ask, onopen, onchanged } = $props();

  /** Отдать карточке список из ответа — только своей вакансии: ответ о
   *  прежней, приехавший после выбора другой, встал бы под неё. */
  function take(done) {
    if (done.vacancy_id === vacancyId) onchanged(done.contacts);
  }

  const newContact = contactAdding({
    list: { again: take },
    form: NEW_CARD.contact,
    save: (draft) => call('vacancies.add_contact', { vacancy_id: vacancyId, value: draft.trim() }),
    say: () => {},
  });

  async function remove(contactId) {
    const done = await ask('vacancies.delete_contact', { contact_id: contactId });
    if (done !== null) take(done);
  }
</script>

<VacancyContacts
  {contacts}
  onopen={(value) => onopen(contactHref(value))}
  onadd={() => (newContact.adding = true)}
  onremove={remove}
/>

{#if newContact.adding}
  <AddressDialog
    kind="contact"
    value={newContact.draft}
    trouble={newContact.trouble}
    saving={newContact.saving}
    ready={newContact.ready}
    oninput={(text) => (newContact.draft = text)}
    onadd={() => newContact.create()}
    onclose={() => (newContact.adding = false)}
  />
{/if}
