<script>
  // Пункт бокового меню. Подпись прячет оформление, когда меню свёрнуто.
  let { icon, label, active, onpick } = $props();
</script>

<button class="nav-group" class:active type="button" title={label} onclick={() => onpick()}>
  <div class="nav-icon-rail"><span class="material-symbols-outlined">{icon}</span></div>
  <span class="nav-label">{label}</span>
</button>
