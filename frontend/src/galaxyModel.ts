export type Planet = { id: string; content_hash?: string|null; member_ids?: string[]; group_id?: string; status?: string; parent_outside_view?: boolean; parent_id: string | null; name: string; sheet: string; version: number; created_at: string; rows: number; column_count: number; lifecycle: string; available: boolean; operation: string };
export type Flight = { id: string; before_id?:string; after_id?:string; source: string; target: string; label: string; columns: string[]; details: Record<string, unknown>; created_at: string; changed_rows: number | null; matched_rows: number | null; status_counts: Record<string, number>; column_stats: {column: string; changed_rows?: number; match_count?: number}[] };
export type FileGroup = {id:string;name:string;sheet:string;bucket:string};
export type Constellation = { groups?: FileGroup[]; next_cursor?: string|null; ancestry_incomplete?: boolean; nodes: Planet[]; edges: Flight[]; source_name: string; sheet: string; truncated: boolean; limit: number };
export function planetColor(node: Planet) {
  return !node.available ? '#88909f' : node.operation === 'regex_replace' ? '#b3a0ff' : node.operation === 'date_normalize' ? '#65dce5' : node.operation === 'categorize' ? '#f3a98c' : node.parent_id ? '#a9dba4' : '#e7c17d';
}
export function planetKind(node: Planet) {
  if(node.status && node.status !== 'READY') return node.status === 'FAILED' ? 'Failed attempt' : node.status === 'CANCELLED' ? 'Cancelled attempt' : 'Import / processing';
  return node.operation === 'regex_replace' ? 'Regex result' : node.operation === 'date_normalize' ? 'Dates result' : node.operation === 'categorize' ? 'Category result' : node.parent_id ? 'Transformed version' : 'Original import';
}
// Stable file constellations. Geometry groups versions; only persisted edges imply operations.
export function positionPlanets(data: Constellation): (Planet & {x:number;y:number;z:number;fx:number;fy:number;fz:number})[] {
  const families = new Map<string, Planet[]>();
  for (const node of data.nodes) {
    const key = node.group_id || 'focused-file';
    families.set(key, [...(families.get(key) || []), node]);
  }
  const clusters = [...families.values()].map(members => {
    const sorted = [...members].sort((a,b)=>a.version-b.version || a.id.localeCompare(b.id));
    return sorted.map((node,i)=>{
      // Golden-angle placement packs repeated imports and branches into a compact disk.
      const radius = i === 0 ? 0 : 88 * Math.sqrt(i);
      const angle = i * 2.399963229728653;
      return {...node,x:radius*Math.cos(angle),y:radius*Math.sin(angle),z:Math.sin(i*1.7)*14};
    });
  });
  const columns = Math.ceil(Math.sqrt(clusters.length));
  const rows = Math.ceil(clusters.length / (columns || 1));
  const extent = Math.max(0,...clusters.flatMap(nodes=>nodes.map(n=>Math.hypot(n.x,n.y))));
  const pitch = Math.max(260,extent*2+140);
  return clusters.flatMap((nodes,i)=>nodes.map(n=>{
    const x=n.x+(i%columns-(columns-1)/2)*pitch;
    const y=n.y- (Math.floor(i/columns)-(rows-1)/2)*pitch;
    return {...n,x,y,fx:x,fy:y,fz:n.z};
  }));
}

export function cameraFrame(nodes:{x:number;y:number;z:number}[],aspect:number,fov:number) {
  const minX=Math.min(...(nodes.length?nodes.map(n=>n.x):[0]))-52, maxX=Math.max(...(nodes.length?nodes.map(n=>n.x):[0]))+52;
  const minY=Math.min(...(nodes.length?nodes.map(n=>n.y):[0]))-58, maxY=Math.max(...(nodes.length?nodes.map(n=>n.y):[0]))+90;
  const halfFov=Math.tan(fov*Math.PI/360);
  const distance=Math.max(230,(maxY-minY)/(2*halfFov),(maxX-minX)/(2*halfFov*Math.max(.2,aspect)))+28;
  return {x:(minX+maxX)/2,y:(minY+maxY)/2,distance,minDistance:110,maxDistance:distance*1.9};
}

// Collapse only proven equal content inside the same source family and lifecycle.
// Persisted records and Tasks stay intact; edges retain their actual before/after IDs.
export function distinctVersions(data: Constellation): Constellation {
  const aliases = new Map<string, string>();
  const unique = new Map<string, Planet>();
  for (const node of [...data.nodes].sort((a,b)=>a.version-b.version || a.id.localeCompare(b.id))) {
    if (node.status && node.status !== 'READY') continue;
    const key = JSON.stringify([node.group_id || 'focused-file', node.lifecycle,
      node.content_hash || node.id]);
    const existing = unique.get(key);
    if (existing) {
      aliases.set(node.id, existing.id);
      existing.member_ids!.push(node.id);
      if (node.created_at > existing.created_at) existing.created_at = node.created_at;
    } else {
      aliases.set(node.id, node.id);
      unique.set(key, {...node, member_ids:[node.id]});
    }
  }
  const counts = new Map<string,number>();
  const nodes = [...unique.values()].map(node=>{
    const family = node.group_id || 'focused-file';
    const version = (counts.get(family)||0)+1;counts.set(family,version);
    const parent = node.parent_id ? aliases.get(node.parent_id) || node.parent_id : null;
    return {...node, version, parent_id:parent===node.id?null:parent};
  });
  const edges = data.edges.flatMap(edge=>{
    const source=aliases.get(edge.source), target=aliases.get(edge.target);
    return source&&target&&source!==target ? [{...edge,source,target,
      before_id:edge.source,after_id:edge.target}] : [];
  });
  return {...data,nodes,edges};
}
