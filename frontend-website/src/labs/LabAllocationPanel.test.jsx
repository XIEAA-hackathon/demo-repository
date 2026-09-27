import { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LabAllocationPanel from './LabAllocationPanel'
import { applyLabChange } from './labBoard'

const team = { id: 1, team_name: 'Alpha', team_code: 'T-001', effective_problem: { id: 7, number: 'WC-7', title: 'Final wildcard problem' }, assignment_id: 1, version: 1, current_lab_id: 1 };
const pending = { id: 2, team_name: 'Pending team', team_code: 'T-002', effective_problem: { id: 8, number: 'R1-8', title: 'Other final problem' } };
const board = { can_move: true, labs: [{ id: 1, name: 'Lab A', occupancy: 1, capacity: 3, teams: [team] }, { id: 2, name: 'Lab B', occupancy: 0, capacity: 3, teams: [] }, { id: 3, name: 'Lab C', occupancy: 0, capacity: 3, teams: [] }], teams: [team, pending], unassigned_team_ids: [2], message: 'Ready' };
let root, host;
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
function Harness({ initial = board, onMove, view = 'labs' }) {
  const [value, setValue] = useState(initial);
  return <LabAllocationPanel board={value} onBoardChange={setValue} onMove={onMove} canMove view={view} />;
}
const render = async props => act(async () => root.render(<Harness {...props} />));
const bucket = name => host.querySelector(`article[aria-label="${name}"]`);
const teamNames = () => [...host.querySelectorAll('.team-allotment-row .team-identity strong')].map(row => row.textContent);
function selectValue(element, value) {
  Object.getOwnPropertyDescriptor(element.constructor.prototype, 'value').set.call(element, value);
  element.dispatchEvent(new Event(element.type === 'search' ? 'input' : 'change', { bubbles: true }));
}
function drop(teamId, target) {
  const event = new Event('drop', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'dataTransfer', { value: { getData: () => String(teamId) } });
  act(() => bucket(target).dispatchEvent(event));
}
it('moves provisionally, rolls back a rejection, and displays the server error', async () => {
  let reject;
  const onMove = vi.fn(() => new Promise((_, no) => { reject = no; }));
  await render({ onMove }); drop(1, 'Lab B');
  expect(bucket('Lab B').textContent).toContain('Alpha');
  expect(bucket('Lab A').textContent).not.toContain('Alpha');
  expect(onMove).toHaveBeenCalledWith(1, { lab_id: 2, expected_version: 1 });
  await act(async () => reject(new Error('Lab B is now full.')));
  expect(bucket('Lab A').textContent).toContain('Alpha');
  expect(bucket('Lab B').textContent).not.toContain('Alpha');
  expect(host.querySelector('[role="alert"]').textContent).toContain('Lab B is now full.');
});
it('keeps accepted placement and can place an unassigned team', async () => {
  const onMove = vi.fn(async (id, payload) => ({ team_id: id, assignment_id: id, version: 2, lab: { id: payload.lab_id, name: 'Lab B' } }));
  await render({ onMove });
  await act(async () => drop(1, 'Lab B'));
  expect(bucket('Lab B').textContent).toContain('Alpha');
  expect(host.textContent).toContain('Assignment updated');
  await act(async () => drop(2, 'Lab B'));
  expect(bucket('Lab B').textContent).toContain('Pending team');
  expect(host.querySelector('[aria-label="Unassigned Teams"]').textContent).toContain('0');
});
it('rejects full and duplicate-PS targets and prevents moves before completion', async () => {
  const duplicate = { ...team, id: 3, team_name: 'Nova', current_lab_id: 2 };
  const initial = { ...board, labs: [board.labs[0], { ...board.labs[1], occupancy: 1, teams: [duplicate] }, { ...board.labs[2], capacity: 1, occupancy: 1, teams: [pending] }] };
  const onMove = vi.fn(); await render({ initial, onMove });
  drop(1, 'Lab B'); expect(host.textContent).toContain('already contains Nova');
  drop(1, 'Lab C'); expect(host.textContent).toContain('Lab C is full');
  expect(onMove).not.toHaveBeenCalled();
  await act(async () => root.unmount()); root = createRoot(host);
  await render({ initial: { ...board, can_move: false }, onMove });
  drop(1, 'Lab B'); expect(onMove).not.toHaveBeenCalled();
  expect(host.textContent).toContain('after Wildcard is complete');
  expect(host.querySelector('[draggable="true"]')).toBeNull();
});
it('keeps team rows lightweight while searching already-loaded problem data', async () => {
  await render({ view: 'teams' });
  expect(host.textContent).toContain('Alpha'); expect(host.textContent).toContain('Lab A');
  expect(host.textContent).toContain('Not assigned'); expect(host.textContent).toContain('View Details');
  expect(host.querySelector('.team-allotment-list').textContent).not.toContain('Final wildcard problem');
  const input = host.querySelector('input');
  act(() => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'WC-7'); input.dispatchEvent(new Event('input', { bubbles: true })); });
  expect(host.textContent).toContain('Alpha'); expect(host.textContent).not.toContain('Pending team');
});
it('filters allocation status from visible lab membership and combines it with search', async () => {
  const teamA = { ...team, team_name: 'Team A', current_lab_id: undefined };
  const teamB = { ...pending, id: 3, team_name: 'Team B' };
  const teamC = { ...pending, id: 4, team_name: 'Team C' };
  const initial = {
    ...board,
    teams: [teamA, teamB, teamC],
    labs: [
      { ...board.labs[0], name: 'CC Lab', occupancy: 1, teams: [{ ...teamA, current_lab_id: 1 }] },
      { ...board.labs[1], name: 'Network Lab', occupancy: 1, teams: [{ ...teamB, current_lab_id: 2 }] },
    ],
    unassigned_team_ids: [teamC.id],
  };
  await render({ initial, view: 'teams' });
  const search = host.querySelector('input[type="search"]');
  const status = host.querySelector('select');

  expect(teamNames()).toEqual(['Team A', 'Team B', 'Team C']);
  expect(host.querySelector('.team-allotment-row').textContent).toContain('CC Lab');
  act(() => selectValue(status, 'allocated'));
  expect(teamNames()).toEqual(['Team A', 'Team B']);
  act(() => selectValue(search, 'Team A'));
  expect(teamNames()).toEqual(['Team A']);
  act(() => selectValue(search, 'Team C'));
  expect(teamNames()).toEqual([]);
  act(() => selectValue(status, 'pending'));
  expect(teamNames()).toEqual(['Team C']);
  act(() => selectValue(search, ''));
  expect(teamNames()).toEqual(['Team C']);
});
it('keeps realtime lab additions and moves in the Allocated filter without a reload', async () => {
  let current = board;
  const renderCurrent = () => act(async () => root.render(<LabAllocationPanel board={current} view="teams" />));
  await renderCurrent();
  act(() => selectValue(host.querySelector('select'), 'allocated'));
  expect(teamNames()).toEqual(['Alpha']);

  current = applyLabChange(current, { team_id: 2, assignment_id: 2, version: 1, lab: { id: 2, name: 'Lab B' } });
  await renderCurrent();
  expect(teamNames()).toEqual(['Alpha', 'Pending team']);

  current = applyLabChange(current, { team_id: 1, assignment_id: 1, version: 2, lab: { id: 3, name: 'Lab C' } });
  await renderCurrent();
  expect(teamNames()).toEqual(['Alpha', 'Pending team']);
  expect(host.querySelectorAll('.team-allotment-row')[0].textContent).toContain('Lab C');
});
it('ignores a stale move delta', () => {
  const updated = applyLabChange(board, { team_id: 1, assignment_id: 1, version: 3, lab: { id: 3, name: 'Lab C' } });
  expect(applyLabChange(updated, { team_id: 1, assignment_id: 1, version: 2, lab: { id: 2, name: 'Lab B' } })).toBe(updated);
});
