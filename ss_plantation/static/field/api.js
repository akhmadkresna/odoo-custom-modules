import { getMeta } from './db.js';

const BASE = '/plantation/field/api/';

export class ApiError extends Error {
  constructor(kind, message, status) {
    super(message);
    this.kind = kind; // 'network' | 'unauthorized' | 'server'
    this.status = status;
  }
}

export async function call(path, { method = 'GET', body, token, timeout = 20000, credentials = 'omit' } = {}) {
  token = token === undefined ? await getMeta('token') : token;
  const headers = {};
  if (token) headers.Authorization = 'Bearer ' + token;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(BASE + path, {
      method, headers, credentials, signal: controller.signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new ApiError('network', 'network', 0);
  } finally {
    clearTimeout(timer);
  }
  const isJson = (response.headers.get('content-type') || '').includes('application/json');
  if (response.status === 401 || (!isJson && (response.redirected || response.status === 403))) {
    throw new ApiError('unauthorized', 'unauthorized', response.status);
  }
  if (!response.ok || !isJson) throw new ApiError('server', 'server', response.status);
  return response.json();
}
