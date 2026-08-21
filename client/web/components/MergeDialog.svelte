<script>
  // Окно слияния карточки: в кого влить нынешнюю.
  //
  // Своим объявлением, потому что сливают двоих — человека и компанию, — а
  // окно у них одно: тот же значок, тот же перечень кандидатов, та же подпись
  // кнопки. Своими остаются слова и то, чем собирается строка кандидата, — они
  // и приходят доводами.
  //
  // Предупреждение о необратимом сюда не входит: у человека и у компании
  // теряется при слиянии разное, и слова там несущие.
  import PickerDialog from './PickerDialog.svelte';
  import PickerRow from './PickerRow.svelte';

  let { title, placeholder, empty, load, asRow, onapply, onclose } = $props();
</script>

<PickerDialog
  icon="merge"
  {title}
  {placeholder}
  {empty}
  {load}
  applyLabel="Слить"
  {onapply}
  {onclose}
>
  {#snippet children(rows, marked, pick)}
    {#each rows as one (one.id)}
      <PickerRow row={asRow(one)} chosen={one.id === marked} onpick={pick} />
    {/each}
  {/snippet}
</PickerDialog>
