<script>
  // Стек записи анкеты: выбор из навыков, заведённых в анкете.
  import SkillPicker from './SkillPicker.svelte';

  let { chosen, known, onedit } = $props();
</script>

<div class="list-block">
  <div class="field-label"><span>Стек</span></div>
  <SkillPicker
    {chosen}
    {known}
    onadd={(name) => onedit({ skill_names: [...chosen, name] })}
    onremove={(index) => onedit({ skill_names: chosen.filter((_, at) => at !== index) })}
  />
</div>
