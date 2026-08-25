<script>
  // Пилюли в форме заведения: подпись, а за ней набор, который правят по одной.
  //
  // Своим объявлением по тому же доводу, что и заметки рядом (`DraftNotes`):
  // наборов таких в формах несколько — две половины стека вакансии и
  // написания компании, — и каждый раз это одна и та же пара обработчиков над
  // полем черновика. Написанные порознь, они разъезжаются молча.
  //
  // Черновик правится на месте: он приходит своим объектом от того, кто его
  // потом и отправит; какое поле в нём набирают — говорит `field`.
  import ChipList from './ChipList.svelte';

  let { draft, field, caption } = $props();
</script>

<div class="captioned-field">
  <div class="field-caption">{caption}</div>
  <ChipList
    items={draft[field]}
    onadd={(one) => (draft[field] = [...draft[field], one])}
    onremove={(index) => (draft[field] = draft[field].filter((_, at) => at !== index))}
  />
</div>
