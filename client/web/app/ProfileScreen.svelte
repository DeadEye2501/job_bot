<script>
  // Раздел «Профиль»: три вкладки одного домена.
  //
  // Вкладка сама читает своё при появлении и сама же гасит своё при уходе:
  // держать всё три разом значило бы спрашивать мост о том, чего никто не
  // видит.

  import TopTabs from '$components/TopTabs.svelte';
  import { PROFILE_TABS } from '$state/sections.js';

  import ProfileCv from './ProfileCv.svelte';
  import ProfileExperience from './ProfileExperience.svelte';
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
  {:else}
    <ProfileExperience {ask} />
  {/if}
</div>
