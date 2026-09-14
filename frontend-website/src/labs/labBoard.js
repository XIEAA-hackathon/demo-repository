export function applyLabChange(board, change) {
  if (!board || !change.lab) return board;
  const existing = board.labs.flatMap(lab => lab.teams).find(team => team.id === change.team_id);
  if (existing && change.assignment_id && (existing.assignment_id > change.assignment_id
      || (existing.assignment_id === change.assignment_id && existing.version > change.version))) return board;
  const team = existing || board.teams.find(row => row.id === change.team_id);
  if (!team || !board.labs.some(lab => lab.id === change.lab.id)) return board;
  const moved = { ...team, ...change, id: team.id, current_lab_id: change.lab.id };
  return { ...board, unassigned_team_ids: board.unassigned_team_ids.filter(id => id !== team.id),
    labs: board.labs.map(lab => {
      const teams = lab.teams.filter(row => row.id !== team.id);
      if (lab.id === change.lab.id) teams.push(moved);
      return { ...lab, teams, occupancy: teams.length };
    }),
  };
}

export function invalidDrop(team, lab) {
  if (!team.effective_problem) return 'Final problem pending';
  if (lab.id === team.current_lab_id) return 'Current lab';
  if (lab.occupancy >= lab.capacity) return `${lab.name} is full (${lab.occupancy}/${lab.capacity}).`;
  const duplicate = lab.teams.find(row => row.id !== team.id && row.effective_problem?.id === team.effective_problem.id);
  return duplicate ? `${lab.name} already contains ${duplicate.team_name} with Problem ${team.effective_problem.number}.` : '';
}
