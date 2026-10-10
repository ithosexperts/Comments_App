/*
 * Optional cross-origin iframe bridge.
 * Add this script to One Portal's authenticated page shell only when comments
 * are launched from a different-origin app iframe. Set
 * window.ONEPORTAL_COMMENTS_ALLOWED_ORIGINS to exact trusted origins before load.
 * Same-origin forms can call /api/comments/launch-ticket directly and do not
 * need this bridge.
 */
(function () {
  'use strict';

  const allowedOrigins = Array.isArray(window.ONEPORTAL_COMMENTS_ALLOWED_ORIGINS)
    ? window.ONEPORTAL_COMMENTS_ALLOWED_ORIGINS
    : [];

  window.addEventListener('message', async function (event) {
    const data = event.data;
    if (!data || data.type !== 'ONEPORTAL_COMMENTS_LAUNCH_REQUEST') return;
    if (!event.source || !allowedOrigins.includes(event.origin)) return;

    const reply = { type: 'ONEPORTAL_COMMENTS_LAUNCH_TICKET', requestId: data.requestId };
    try {
      const context = data.context || {};
      const token = localStorage.getItem('access_token') || localStorage.getItem('auth_token');
      if (!token) throw new Error('No active One Portal login. Please sign in again.');

      const response = await fetch(window.location.origin + '/api/comments/launch-ticket', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({
          tableName: context.tableName,
          fmsRefId: context.fmsRefId,
          appId: context.appId,
          stageNo: context.stageNo
        })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ticket) {
        throw new Error(result.detail || result.message || 'Could not issue a Comments launch ticket.');
      }
      reply.ticket = result.ticket;
    } catch (error) {
      reply.error = String(error && error.message || error || 'Comments launch failed.');
    }
    event.source.postMessage(reply, event.origin);
  });
})();
