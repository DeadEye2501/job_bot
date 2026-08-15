<script>
  // Кружок рядом с именем: снимок, буквы имени или значок предмета.
  //
  // Три вида одного места, и порядок между ними несущий: снимок узнаётся
  // быстрее всего, буквы хотя бы различают соседние строки, а значок говорит
  // только род — им и заканчивают, когда сказать больше нечего.
  import { initials } from '$state/contacts.js';

  let { avatar = null, name = '', icon } = $props();

  const letters = $derived(initials(name));
</script>

{#if avatar}
  <img class="hr-avatar" src={avatar} alt="" />
{:else if letters}
  <span class="hr-avatar">{letters}</span>
{:else}
  <span class="hr-avatar"><span class="material-symbols-outlined">{icon}</span></span>
{/if}
