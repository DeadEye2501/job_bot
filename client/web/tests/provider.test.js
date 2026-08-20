// Следствия разговора с поставщиком моделей: что экран узнаёт о нём и как
// различает беду и пустоту.
//
// Мост подделан: предмет здесь не он, а два ответа, которые нельзя путать, —
// «поставщик не отозвался» и «поставщик не держит ни одной модели».

import { describe, expect, it } from 'vitest';

import { askModels, probeModel } from '../state/provider.js';

/** Отказ моста в том виде, в каком его поднимает обёртка зова. */
function refusal(message) {
  const trouble = new Error(message);
  trouble.name = 'Refused';
  return trouble;
}

const CREDS = { kind: 'chat', base_url: 'http://localhost:1234/v1', api_key: 'k', model: 'qwen' };

describe('перечень моделей у поставщика', () => {
  it('имена приходят перечнем', async () => {
    const call = async () => ({ models: ['qwen', 'llama'] });

    expect(await askModels(call, CREDS)).toEqual({ models: ['qwen', 'llama'], trouble: '' });
  });

  it('неподнятый поставщик отличим от пустого', async () => {
    // Иначе шаг мастера объявляет недоступный сервер «не вернувшим ни одной
    // модели», и человек идёт грузить модель вместо того, чтобы поднять сервер.
    const call = async () => {
      throw refusal('Соединение отклонено');
    };

    expect(await askModels(call, CREDS)).toEqual({ models: [], trouble: 'Соединение отклонено' });
  });

  it('пустой перечень бедой не считается', async () => {
    const call = async () => ({ models: [] });

    expect(await askModels(call, CREDS)).toEqual({ models: [], trouble: '' });
  });

  it('ответ без перечня читается как пустой', async () => {
    // Поле может и не приехать: сервер чужой, и договор его ответа не наш.
    const call = async () => ({});

    expect(await askModels(call, CREDS)).toEqual({ models: [], trouble: '' });
  });

  it('спрашивают адрес и ключ, а имя модели не спрашивают', async () => {
    // Перечень читается с адреса и ключа; имя модели — как раз то, что ищут.
    const asked = [];
    const call = async (path, payload) => {
      asked.push({ path, payload });
      return { models: [] };
    };

    await askModels(call, CREDS);

    expect(asked).toEqual([
      {
        path: 'settings.list_models',
        payload: { kind: 'chat', base_url: 'http://localhost:1234/v1', api_key: 'k' },
      },
    ]);
  });
});

describe('проверка связи с поставщиком', () => {
  it('удача называет модель и задержку', async () => {
    const call = async () => ({ model: 'qwen', latency_ms: 42 });

    expect(await probeModel(call, CREDS)).toEqual({
      ok: true,
      model: 'qwen',
      latencyMs: 42,
      trouble: '',
    });
  });

  it('отказ приходит своей фразой, а не общим словом', async () => {
    // Фраза поставщика — и есть исход проверки: по ней человек и разбирается,
    // что не так с адресом, ключом или самой моделью.
    const call = async () => {
      throw refusal('Модель qwen не найдена');
    };

    expect(await probeModel(call, CREDS)).toEqual({
      ok: false,
      model: '',
      latencyMs: 0,
      trouble: 'Модель qwen не найдена',
    });
  });

  it('проверяют набранное целиком, вместе с именем модели', async () => {
    const asked = [];
    const call = async (path, payload) => {
      asked.push({ path, payload });
      return { model: 'qwen', latency_ms: 1 };
    };

    await probeModel(call, CREDS);

    expect(asked).toEqual([{ path: 'settings.probe_model', payload: CREDS }]);
  });
});
