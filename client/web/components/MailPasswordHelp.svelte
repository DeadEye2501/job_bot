<script>
  // Где взять пароль приложения для почты: что это такое и путь в настройках
  // популярных почт. Адреса нажимаются: открывает их система, а не окно —
  // окно раздаёт свою папку, а не интернет.
  import ModalHead from './ModalHead.svelte';
  import ModalShell from './ModalShell.svelte';

  let { onopen, onclose } = $props();
</script>

{#snippet link(url, text)}
  <button class="help-link" type="button" onclick={() => onopen(url)}>{text}</button>
{/snippet}

<ModalShell extra="narrow roomy" {onclose}>
  {#snippet children()}
    <ModalHead icon="help" title="Пароль приложения" {onclose} />
    <div class="modal-body help">
      <p>
        Это отдельный пароль, который почта выдаёт программам, отправляющим письма от вашего
        имени. Обычный пароль от ящика не подойдёт: почта не пускает с ним сторонние программы.
      </p>

      <p><strong>Gmail</strong></p>
      <ol>
        <li>Откройте {@render link('https://myaccount.google.com/security', 'myaccount.google.com')} → «Безопасность».</li>
        <li>Включите двухэтапную аутентификацию, если она выключена: без неё паролей приложений нет.</li>
        <li>Откройте «Пароли приложений» — там же или поиском по настройкам аккаунта.</li>
        <li>Впишите название, например «Job Bot», и нажмите «Создать».</li>
        <li>Google покажет 16-значный пароль. Скопируйте его сразу: второй раз он не покажется.</li>
      </ol>

      <p><strong>Яндекс</strong></p>
      <ol>
        <li>Откройте {@render link('https://id.yandex.ru/security', 'id.yandex.ru')} → «Безопасность».</li>
        <li>В разделе «Пароли приложений» выберите «Почта».</li>
        <li>Впишите название, например «Job Bot», и нажмите «Создать».</li>
        <li>Яндекс покажет пароль. Скопируйте его сразу: второй раз он не покажется.</li>
        <li>
          В настройках Яндекс Почты откройте «Почтовые программы» и разрешите вход по паролям
          приложений: без этого почта его не примет.
        </li>
      </ol>

      <p><strong>Mail.ru</strong></p>
      <ol>
        <li>Откройте {@render link('https://account.mail.ru', 'account.mail.ru')} → «Безопасность».</li>
        <li>Найдите «Пароли для внешних приложений» и нажмите «Добавить».</li>
        <li>Впишите название, например «Job Bot», и нажмите «Продолжить».</li>
        <li>Mail.ru покажет пароль. Скопируйте его сразу: второй раз он не покажется.</li>
      </ol>
    </div>
  {/snippet}
</ModalShell>
