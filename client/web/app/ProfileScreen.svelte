<script>
  // Раздел «Профиль»: четыре вкладки одного домена.
  //
  // Вкладка сама читает своё при появлении и сама же гасит своё при уходе:
  // держать все разом значило бы спрашивать мост о том, чего никто не видит.

  import ExperienceCard from '$components/ExperienceCard.svelte';
  import ProjectCard from '$components/ProjectCard.svelte';
  import TopTabs from '$components/TopTabs.svelte';
  import { EXPERIENCE } from '$state/experience.js';
  import { PROJECTS } from '$state/projects.js';
  import { PROFILE_TABS } from '$state/sections.js';

  import ProfileCv from './ProfileCv.svelte';
  import ProfileRecords from './ProfileRecords.svelte';
  import ProfileSkills from './ProfileSkills.svelte';

  let { ask } = $props();

  let tab = $state(PROFILE_TABS[0].key);
</script>

<TopTabs tabs={PROFILE_TABS} active={tab} onpick={(key) => (tab = key)} />

<div class="screen-body">
  {#if tab === 'cv'}
    <ProfileCv {ask} />
  {:else if tab === 'skills'}
    <ProfileSkills {ask} />
  {:else if tab === 'experience'}
    <ProfileRecords {ask} kind={EXPERIENCE} Card={ExperienceCard} />
  {:else}
    <ProfileRecords {ask} kind={PROJECTS} Card={ProjectCard} />
  {/if}
</div>
