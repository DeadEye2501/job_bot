<script>
  // Многострочное поле анкеты: набранное уходит с задержкой, а по уходу из
  // поля и по Ctrl+Enter — сразу.
  //
  // Своим объявлением, потому что таких полей в анкете два — образование и
  // предпочтения, — и тройка обработчиков у них написана одинаково. Забудь
  // одна копия немедленную запись, набранное в ней терялось бы при переходе к
  // соседнему полю, и заметил бы это человек не сразу.
  //
  // Однострочные поля анкеты сюда не сведены: они рисуются перебором по
  // описанию полей, и своего тела у них нет вовсе.
  //
  // Записью распоряжается сама анкета: у неё одна отложенная запись на всю
  // страницу, и поле про неё знает только то, чем её позвать.
  import { growing } from '$state/autosize.js';
  import { saveKey } from '$state/keys.js';

  let { value, maxlength, placeholder, lines, ontyped, onflush } = $props();
</script>

<textarea
  class="textarea span-2"
  rows="1"
  data-lines={lines}
  use:growing={value}
  {maxlength}
  {placeholder}
  {value}
  oninput={(event) => ontyped(event.currentTarget.value)}
  onblur={() => onflush()}
  onkeydown={(event) => saveKey(event) && onflush()}
></textarea>
