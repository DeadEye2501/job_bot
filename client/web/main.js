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
import './styles/spin.css';
import './styles/shell.css';
import './styles/wizard.css';
import './styles/status-row.css';
import './styles/radio-card.css';
import './styles/file-pick.css';
import './styles/note-card.css';
import './styles/help-block.css';
import './styles/nav.css';
import './styles/tabs.css';
import './styles/button.css';
import './styles/icon-button.css';
import './styles/trash.css';
import './styles/bar.css';
import './styles/modal.css';
import './styles/tg-login.css';
import './styles/footer.css';
import './styles/input.css';
import './styles/inline-edit.css';
import './styles/search-box.css';
import './styles/checkbox.css';
import './styles/empty-note.css';
import './styles/count-pill.css';
import './styles/status-pill.css';
import './styles/logs.css';
import './styles/log-level-pill.css';
import './styles/log-row.css';
import './styles/screen.css';
import './styles/form-grid.css';
import './styles/autosave-error.css';
import './styles/slider.css';
import './styles/dropdown.css';
import './styles/chips.css';
import './styles/settings.css';
import './styles/settings-section.css';
import './styles/pipeline.css';
import './styles/choice-row.css';
import './styles/lang-rows.css';
import './styles/cv-file.css';
import './styles/new-box.css';
import './styles/collapsible.css';
import './styles/collapse-arrow.css';
import './styles/toggle.css';
import './styles/master-detail.css';
import './styles/contacts-layout.css';
import './styles/contacts.css';
import './styles/card-section.css';
import './styles/contact-card.css';
import './styles/mini-list.css';
import './styles/chat.css';
import './styles/channel-stats.css';
import './styles/add-channel.css';
import './styles/blacklist.css';
import './styles/blacklist-dialog.css';
import './styles/vacancies.css';
import './styles/vacancy-card.css';
import './styles/matched-chip.css';
import './styles/contact-block.css';
import './styles/unnamed.css';
import './styles/raw-text.css';
import './styles/picker.css';
import './styles/popover.css';
import './styles/menu.css';
import './styles/status-picker.css';
import './styles/timeline.css';
import './styles/notes-area.css';
import './styles/vacancy-filters.css';
import './styles/filter-group.css';
import './styles/pick-list.css';
import './styles/date-picker.css';
import './styles/pill.css';
import './styles/big-number.css';
import './styles/ruled-row.css';
import './styles/accent-fill.css';
import './styles/stats.css';
import './styles/stats-status.css';
import './styles/stats-skills.css';
import './styles/stats-responses.css';
import './styles/stats-channels.css';
// Ниже оформления самих блоков, и по тому же уговору, что у соседа-заливки:
// у наведения та же весомость селектора, и выигрывает порядок.
import './styles/accent-outline.css';
import './styles/donut.css';
import './styles/status-color.css';
import './styles/skills.css';
import './styles/experience.css';
import './styles/bullet-list.css';
import './styles/skill-picker.css';
import './styles/health-lamp.css';
import './styles/mode.css';
import './styles/progress.css';
import './styles/run.css';
import './styles/unread.css';
import './styles/plaque.css';

import { mount } from 'svelte';

import Shell from './app/Shell.svelte';

mount(Shell, { target: document.getElementById('app') });
