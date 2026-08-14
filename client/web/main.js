// Точка входа страницы: собирает оформление и поднимает оболочку окна.
//
// Оформление ввозится поимённо и здесь, а не в компонентах: подключённый файл
// Svelte ограничить не может, и порядок правил в общем пространстве зависит от
// порядка ввоза. Держать этот порядок в одном месте — единственный способ не
// гадать, чей отступ победил.
//
// Палитра идёт первой: остальные файлы берут цвет только через её переменные,
// и объявленная позже она не успела бы к их правилам.
import 'material-symbols/outlined.css';

import './styles/palette.css';
import './styles/base.css';
import './styles/shell.css';
import './styles/nav.css';
import './styles/tabs.css';
import './styles/button.css';
import './styles/icon-button.css';
import './styles/modal.css';
import './styles/footer.css';
import './styles/logs.css';
import './styles/log-level-pill.css';
import './styles/log-row.css';
import './styles/health-lamp.css';
import './styles/mode.css';
import './styles/progress.css';
import './styles/run.css';
import './styles/unread.css';
import './styles/plaque.css';

import { mount } from 'svelte';

import Shell from './app/Shell.svelte';

mount(Shell, { target: document.getElementById('app') });
