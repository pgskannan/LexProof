const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');
const {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} = require('@firebase/rules-unit-testing');

const rules = fs.readFileSync(
  path.join(__dirname, '..', '..', 'firestore.rules'),
  'utf8',
);

let testEnv;

const evidence = (ownerId) => ({
  evidence_id: 'evidence-1',
  passport_id: 'passport-1',
  owner_id: ownerId,
  content: 'Evidence',
});

const anchor = {
  evidence_id: 'evidence-1',
  passport_id: 'passport-1',
  blockchain_network: 'ethereum-sepolia',
  evidence_hash: 'a'.repeat(64),
};

const evidenceRef = (firestore, evidenceId = 'evidence-1') =>
  firestore.collection('evidence_records').doc(evidenceId);
const anchorRef = (firestore, evidenceId = 'evidence-1') =>
  firestore.collection('evidence_anchors').doc(evidenceId);

async function seed(withAnchor = false) {
  await testEnv.withSecurityRulesDisabled(async (context) => {
    const firestore = context.firestore();
    await firestore.collection('evidence_records').doc('evidence-1').set(evidence('user-a'));
    await firestore.collection('evidence_records').doc('evidence-2').set(evidence('user-b'));
    if (withAnchor) {
      await firestore.collection('evidence_anchors').doc('evidence-1').set(anchor);
    }
  });
}

test.before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: 'demo-lexproof-rules',
    firestore: { rules },
  });
});

test.beforeEach(async () => {
  await testEnv.clearFirestore();
  await seed();
});

test.after(async () => {
  await testEnv.cleanup();
});

test('anonymous read evidence is denied', async () => {
  const firestore = testEnv.unauthenticatedContext().firestore();
  await assertFails(evidenceRef(firestore).get());
});

test('anonymous create evidence is denied', async () => {
  const firestore = testEnv.unauthenticatedContext().firestore();
  await assertFails(evidenceRef(firestore, 'new').set(evidence('user-a')));
});

test('user A reads own evidence', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertSucceeds(evidenceRef(firestore).get());
});

test('user A cannot read user B evidence', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(evidenceRef(firestore, 'evidence-2').get());
});

test('user A updates own unanchored evidence', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertSucceeds(evidenceRef(firestore).update({ content: 'Updated' }));
});

test('user A cannot update user B evidence', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(evidenceRef(firestore, 'evidence-2').update({ content: 'Updated' }));
});

test('user A cannot change owner_id', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(evidenceRef(firestore).update({ owner_id: 'user-b' }));
});

test('user A cannot update anchored evidence', async () => {
  await seed(true);
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(evidenceRef(firestore).update({ content: 'Updated' }));
});

test('user A cannot delete anchored evidence', async () => {
  await seed(true);
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(evidenceRef(firestore).delete());
});

test('anchor update is denied', async () => {
  await seed(true);
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(anchorRef(firestore).update({ evidence_hash: 'b'.repeat(64) }));
});

test('anchor delete is denied', async () => {
  await seed(true);
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(anchorRef(firestore).delete());
});

test('user A cannot create an anchor for user B evidence', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(anchorRef(firestore, 'evidence-2').set({ ...anchor, evidence_id: 'evidence-2' }));
});

test('user A can create an anchor for own evidence', async () => {
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertSucceeds(anchorRef(firestore).set(anchor));
});

test('user A cannot read user B anchor', async () => {
  await testEnv.withSecurityRulesDisabled(async (context) => {
    await context.firestore().collection('evidence_anchors').doc('evidence-2').set({
      ...anchor,
      evidence_id: 'evidence-2',
    });
  });
  const firestore = testEnv.authenticatedContext('user-a').firestore();
  await assertFails(anchorRef(firestore, 'evidence-2').get());
});
