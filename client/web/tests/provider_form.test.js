// Поля поставщика моделей — правила, общие для шага мастера и настроек: что
// сбрасывается при смене источника, что делает выбор файла, как отбивается
// ответ проверки, пришедший после правки.
//
// Мост подделан по имени метода: предмет здесь не он, а то, что форма делает
// с его ответами.

import { describe, expect, it } from 'vitest';

import { providerForm } from '$state/provider_form.svelte.js';

const SERVER = { base_url: 'http://localhost:1234', api_key: 'k', model: 'qwen' };

/** Мост, отвечающий по имени метода; зовы копятся в `asked`. */
function bridge(replies) {
  const asked = [];
  const call = async (method, payload) => {
    asked.push({ method, payload });
    const reply = replies[method];
    return typeof reply === 'function' ? reply(payload) : reply;
  };
  return { asked, call };
}

function form(replies, alive = { now: true }) {
  const { asked, call } = bridge(replies);
  return { asked, alive, form: providerForm({ kind: 'embed', call, alive }) };
}

/** Ответ, который доедет, когда его отпустят. */
function held() {
  let release;
  const answer = new Promise((resolve) => {
    release = resolve;
  });
  return { answer, release };
}

describe('перечень имён моделей', () => {
  it('спрашивается с набранного адреса и ключа и ложится в подсказку', async () => {
    const { asked, form: f } = form({ 'settings.list_models': { models: ['a', 'b'] } });
    f.creds = SERVER;

    const found = await f.listModels();

    expect(f.models).toEqual(['a', 'b']);
    expect(found.trouble).toBe('');
    expect(asked[0].payload).toEqual({
      kind: 'embed',
      base_url: SERVER.base_url,
      api_key: SERVER.api_key,
    });
  });

  it('пришедший после ухода с экрана никуда не ложится', async () => {
    const alive = { now: true };
    const { form: f } = form({ 'settings.list_models': { models: ['a'] } }, alive);
    const listing = f.listModels();
    alive.now = false;

    await listing;

    expect(f.models).toEqual([]);
  });
});

describe('выбор готового поставщика', () => {
  it('подставляет адрес, сбрасывает имя модели и гасит проверку', async () => {
    const { form: f } = form({
      'settings.probe_model': { model: 'qwen', latency_ms: 5 },
      'settings.list_models': { models: [] },
    });
    f.creds = SERVER;
    await f.verify();

    await f.pickPreset('Ollama');

    expect(f.creds).toEqual({ base_url: 'http://localhost:11434', api_key: 'k', model: '' });
    expect(f.probe.status).toBe('idle');
  });

  it('незнакомое имя не трогает ничего', () => {
    const { asked, form: f } = form({});
    f.creds = SERVER;

    f.pickPreset('нет такого');

    expect(f.creds).toEqual(SERVER);
    expect(asked).toEqual([]);
  });
});

describe('смена источника эмбеддингов', () => {
  it('стирает набранное, подсказку, проверку и галочку «как у чата»', async () => {
    const { form: f } = form({
      'settings.probe_model': { model: 'qwen', latency_ms: 5 },
      'settings.list_models': { models: ['qwen'] },
    });
    f.creds = SERVER;
    f.same = true;
    await f.listModels();
    await f.verify();

    f.switchSource(true);

    expect([f.fromFile, f.same, f.models, f.probe.status]).toEqual([true, false, [], 'idle']);
    expect(f.creds).toEqual({ base_url: '', api_key: '', model: '' });
  });

  it('выбранный заново тот же источник набранное не стирает', () => {
    const { form: f } = form({});
    f.creds = SERVER;
    f.same = true;

    f.switchSource(false);

    expect([f.creds, f.same]).toEqual([SERVER, true]);
  });
});

describe('выбор файла модели', () => {
  it('выбранный путь становится моделью, проверка гаснет', async () => {
    const { form: f } = form({
      'settings.probe_model': { model: 'x', latency_ms: 1 },
      'settings.pick_model_file': { path: 'D:/m.gguf' },
    });
    f.switchSource(true);
    f.creds = { base_url: '', api_key: '', model: 'C:/old.gguf' };
    await f.verify();

    const got = await f.pickFile();

    expect(got).toEqual({ path: 'D:/m.gguf', trouble: '' });
    expect(f.creds).toEqual({ base_url: '', api_key: '', model: 'D:/m.gguf' });
    expect(f.probe.status).toBe('idle');
  });

  it('закрытый диалог не трогает выбранного раньше', async () => {
    const before = { base_url: '', api_key: '', model: 'C:/old.gguf' };
    const { form: f } = form({ 'settings.pick_model_file': { path: '' } });
    f.creds = before;

    const got = await f.pickFile();

    expect(got.path).toBe('');
    expect(f.creds).toEqual(before);
  });

  it('отказ моста отдаётся фразой и не трогает выбранного', async () => {
    const before = { base_url: '', api_key: '', model: 'C:/old.gguf' };
    const { form: f } = form({
      'settings.pick_model_file': () => {
        throw new Error('Диалог не открылся');
      },
    });
    f.creds = before;

    const got = await f.pickFile();

    expect(got.trouble).toBe('Диалог не открылся');
    expect(f.creds).toEqual(before);
  });

  it('путь, пришедший после ухода с экрана, не кладётся и не отдаётся', async () => {
    const alive = { now: true };
    const { form: f } = form({ 'settings.pick_model_file': { path: 'D:/m.gguf' } }, alive);
    const picking = f.pickFile();
    alive.now = false;

    const got = await picking;

    expect(got).toEqual({ path: '', trouble: '' });
    expect(f.creds.model).toBe('');
  });
});

describe('галочка «как у чата»', () => {
  const chat = { base_url: 'http://chat', api_key: 'ck', model: 'chat-model' };

  it('включённая переносит адрес и ключ чата, модель оставляет свою', async () => {
    const { asked, form: f } = form({ 'settings.list_models': { models: [] } });
    f.creds = SERVER;

    await f.useChat(true, chat);

    expect(f.creds).toEqual({ base_url: 'http://chat', api_key: 'ck', model: 'qwen' });
    expect(f.same).toBe(true);
    // Подсказка спрошена с нового адреса: прежняя называла бы модели чужого
    // сервера.
    expect(asked.at(-1).payload.base_url).toBe('http://chat');
  });

  it('снятая только показывает поля: набранное остаётся, спрашивать нечего', async () => {
    const { asked, form: f } = form({});
    f.creds = SERVER;
    f.same = true;

    await f.useChat(false, chat);

    expect([f.creds, f.same, asked]).toEqual([SERVER, false, []]);
  });
});

describe('проверка связи', () => {
  it('удача называет модель и время ответа', async () => {
    const { form: f } = form({ 'settings.probe_model': { model: 'qwen', latency_ms: 42 } });
    f.creds = SERVER;

    await f.verify();

    expect(f.probe).toEqual({ status: 'ok', model: 'qwen', latencyMs: 42, error: '' });
  });

  it('отказ поставщика — исход проверки, а не брошенная беда', async () => {
    const { form: f } = form({
      'settings.probe_model': () => {
        throw new Error('Connection refused');
      },
    });
    f.creds = SERVER;

    await f.verify();

    expect([f.probe.status, f.probe.error]).toEqual(['err', 'Connection refused']);
  });

  it('пока ответа нет, проверка занята', () => {
    const { form: f } = form({ 'settings.probe_model': () => new Promise(() => {}) });
    f.creds = SERVER;

    f.verify();

    expect(f.probe.status).toBe('busy');
  });

  it('ответ, пришедший после правки полей, отбрасывается', async () => {
    const late = held();
    const { form: f } = form({ 'settings.probe_model': () => late.answer });
    f.creds = SERVER;
    const probing = f.verify();

    f.forget();
    late.release({ model: 'qwen', latency_ms: 1 });
    await probing;

    expect(f.probe.status).toBe('idle');
  });

  it('ответ, пришедший после ухода с экрана, не кладётся', async () => {
    const late = held();
    const alive = { now: true };
    const { form: f } = form({ 'settings.probe_model': () => late.answer }, alive);
    f.creds = SERVER;
    const probing = f.verify();

    alive.now = false;
    late.release({ model: 'qwen', latency_ms: 1 });
    await probing;

    expect(f.probe.status).toBe('busy');
  });
});

describe('беда набранного', () => {
  it('у сервера — адрес и имя модели', () => {
    const { form: f } = form({});
    f.creds = { ...SERVER, model: '' };
    expect(f.trouble).toBe('Выберите модель');
  });

  it('у файла модели — сам файл, а не адрес', () => {
    const { form: f } = form({});
    f.fromFile = true;
    f.creds = { base_url: '', api_key: '', model: '' };
    expect(f.trouble).not.toBe('');
    expect(f.trouble).not.toMatch(/адрес/i);
  });

  it('заполненное беды не несёт', () => {
    const { form: f } = form({});
    f.creds = SERVER;
    expect(f.trouble).toBe('');
  });
});
