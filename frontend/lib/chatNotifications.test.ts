import { describe, expect, it } from 'vitest';
import { listChatDeliveriesPath, testChatNotificationRequest } from './chatNotifications';

describe('chat notification request helpers', () => {
  it('builds the deliveries list path with no limit', () => {
    expect(listChatDeliveriesPath('org 1')).toBe('/api/orgs/org%201/chat-notifications/deliveries');
  });

  it('builds the deliveries list path with an explicit limit', () => {
    expect(listChatDeliveriesPath('org-1', 25)).toBe('/api/orgs/org-1/chat-notifications/deliveries?limit=25');
  });

  it('builds the test-notification request', () => {
    expect(testChatNotificationRequest('org 1')).toEqual({
      path: '/api/orgs/org%201/chat-notifications/test',
      method: 'POST',
    });
  });
});
