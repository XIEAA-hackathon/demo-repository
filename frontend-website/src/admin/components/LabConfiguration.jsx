import { useCallback, useEffect, useState } from "react";
import { createLab, deleteLab, getLabs, updateLab } from "../services/api";

const emptyForm = { name: "", capacity: "", sort_order: "0" };

export default function LabConfiguration({ revision = 0 }) {
  const [labs, setLabs] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);

  const load = useCallback(async () => {
    try { setLabs(await getLabs()); setError(""); }
    catch (cause) { setError(cause.message || "Lab configuration could not be loaded."); }
  }, []);
  useEffect(() => { void load(); }, [load, revision]);
  useEffect(() => {
    if (!editing) return undefined;
    const closeOnEscape = (event) => { if (event.key === "Escape" && !working) setEditing(null); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [editing, working]);

  const openCreate = () => { setEditing({ id: null }); setForm({ ...emptyForm, sort_order: String(labs.length) }); setError(""); setNotice(""); };
  const openEdit = (lab) => { setEditing(lab); setForm({ name: lab.name, capacity: String(lab.capacity), sort_order: String(lab.sort_order) }); setError(""); setNotice(""); };
  const save = async (event) => {
    event.preventDefault();
    const capacity = Number(form.capacity);
    const sortOrder = Number(form.sort_order || 0);
    if (!form.name.trim() || !Number.isInteger(capacity) || capacity < 1 || !Number.isInteger(sortOrder) || sortOrder < 0) {
      setError("Enter a lab name, a capacity of at least 1, and a non-negative display order.");
      return;
    }
    setWorking(true); setError("");
    try {
      const payload = { name: form.name.trim(), capacity, sort_order: sortOrder, active: true };
      if (editing.id) await updateLab(editing.id, payload); else await createLab(payload);
      setEditing(null); setNotice("Event lab setup saved."); await load();
    } catch (cause) { setError(cause.message || "Lab setup could not be saved."); }
    finally { setWorking(false); }
  };
  const remove = async (lab) => {
    if (!window.confirm(`Delete ${lab.name}?`)) return;
    setWorking(true); setError(""); setNotice("");
    try { await deleteLab(lab.id); setNotice(`${lab.name} deleted.`); await load(); }
    catch (cause) { setError(cause.message || "Lab could not be deleted."); }
    finally { setWorking(false); }
  };

  return (
    <section className="lab-config-panel">
      <header><div><h3>Lab configuration</h3><p>Physical rooms and their hard seat limits.</p></div><button className="secondary-button" type="button" disabled={working} onClick={openCreate}>+ Create Lab</button></header>
      {error && <div className="lab-inline-error" role="alert">{error}</div>}
      {notice && <div className="lab-config-notice" role="status">{notice}</div>}
      <div className="lab-config-list">
        <div className="lab-config-list__head"><span>Lab name</span><span>Capacity</span><span>Order</span><span>Actions</span></div>
        {labs.map((lab) => <div className="lab-config-row" key={lab.id}><strong>{lab.name}</strong><span>{lab.capacity}</span><span>{lab.sort_order}</span><span><button type="button" disabled={working} onClick={() => openEdit(lab)}>Edit</button><button type="button" disabled={working} onClick={() => void remove(lab)}>Delete</button></span></div>)}
        {!labs.length && <div className="lab-config-empty">No labs configured yet.</div>}
      </div>
      {editing && <div className="lab-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditing(null); }}><form className="lab-modal lab-config-form" role="dialog" aria-modal="true" aria-labelledby="lab-form-title" onSubmit={save}><h3 id="lab-form-title">{editing.id ? "Edit lab" : "Create lab"}</h3><label>Lab name<input value={form.name} maxLength={120} autoFocus onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label><div className="lab-config-form__numbers"><label>Capacity<input type="number" min="1" max="10000" value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} required /></label><label>Display order<input type="number" min="0" max="10000" value={form.sort_order} onChange={(event) => setForm({ ...form, sort_order: event.target.value })} /></label></div><div className="lab-modal__actions"><button className="secondary-button" type="button" onClick={() => setEditing(null)}>Cancel</button><button className="primary-button" type="submit" disabled={working}>{working ? "Saving…" : "Save"}</button></div></form></div>}
    </section>
  );
}
