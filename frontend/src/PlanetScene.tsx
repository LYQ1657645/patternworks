import { useEffect, useRef, useState } from 'react';
import type { Constellation, Planet, Flight } from './galaxyModel';
import { positionPlanets, cameraFrame, planetColor, planetKind } from './galaxyModel';
import { useAppearance } from './motion';
import { nearestProjectedEdge } from './edgePicking';
import { createPlanetVisual, type PlanetVisual } from './planetVisuals';
import { createConstellationCloud } from './constellationCloud';
import { createStarField } from './starField';
import type { ForceGraph3DInstance } from '3d-force-graph';
import * as THREE from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';

type Props = {data:Constellation; selected:string|null; selectedFlight:string|null; active:boolean; previewId?:string|null; focusedGroup?:string|null; onReset?:()=>void; onGroup?:(id:string)=>void; onPlanet:(node:Planet)=>void; onFlight:(edge:Flight)=>void};
export default function PlanetScene({data,selected,selectedFlight,active,onPlanet,onFlight,focusedGroup=null,onReset,onGroup,previewId=null}:Props) {
  const mount=useRef<HTMLDivElement>(null);const graph=useRef<ForceGraph3DInstance|null>(null);
  const focused=!!focusedGroup;
  const focusId=useRef(focusedGroup);focusId.current=focusedGroup;
  const focusCamera=useRef<(id:string|null)=>void>(()=>{});
  useEffect(()=>{focusCamera.current(focusedGroup);setHovered(null);},[focusedGroup]);
  const resetView=useRef<()=>void>(()=>{});
  const previewCamera=useRef<(id:string|null,instant?:boolean)=>void>(()=>{});
  const previewing=useRef(previewId);previewing.current=previewId;
  const hoveredId=useRef<string|null>(null);
  const [hovered,setHovered]=useState<{edge:Flight;x:number;y:number}|null>(null);
  useEffect(()=>{previewCamera.current(previewId);setHovered(null);},[previewId]);
  const labelElements=useRef(new Map<string,HTMLButtonElement>());
  const callbacks=useRef({onPlanet,onFlight,onGroup});callbacks.current={onPlanet,onFlight,onGroup};
  const chosenFlight=useRef(selectedFlight);chosenFlight.current=selectedFlight;
  useEffect(()=>{const g=graph.current;if(g)g.linkColor(g.linkColor()).linkWidth(g.linkWidth()).linkDirectionalParticles(g.linkDirectionalParticles());},[selected,selectedFlight]);
  const [error,setError]=useState('');const [ready,setReady]=useState(false);
  const {reduced}=useAppearance();
  useEffect(()=>{
    if(!active || !mount.current || !data.nodes.length)return;
    const el=mount.current;let disposed=false, stop=()=>{};setReady(false);setError('');hoveredId.current=null;setHovered(null);
    void import('3d-force-graph').then(({default:ForceGraph})=>{
      if(disposed)return;
      const resources:{dispose:()=>void}[]=[];const groups=new Map<string,THREE.Group>();const visuals=new Map<string,PlanetVisual>();let raf=0;
      let g:ForceGraph3DInstance;
      const edgeCurves=new Map<string,THREE.Vector3[]>();
      let edgeAt:(event:MouseEvent|PointerEvent)=>string|null=()=>null;
      const hitRegions:THREE.Object3D[]=[];const anchors=new Map<string,THREE.Vector3>();
      try {
        g=new ForceGraph(el,{controlType:'orbit',rendererConfig:{antialias:true,alpha:true}});
        graph.current=g;
        g.width(el.clientWidth).height(el.clientHeight).backgroundColor('#00000000').showNavInfo(false)
          .enableNodeDrag(false).cooldownTicks(0).nodeRelSize(25)
          .nodeLabel(node=>{const n=node as unknown as Planet;const label=document.createElement('span');label.textContent=`${n.name}${n.sheet?' · '+n.sheet:''} · V${n.version} · ${planetKind(n)}`;return label;})
          .linkLabel('')
          .linkColor(link=>{const e=link as unknown as Flight;const target=typeof e.target==='string'?e.target:(e.target as unknown as Planet).id;const n=data.nodes.find(p=>p.id===target);return n?planetColor(n):'#92a7c9';})
          .linkOpacity(.78).linkWidth(link=>{const id=(link as unknown as Flight).id;return id===hoveredId.current||id===chosenFlight.current?1.9:.85;}).linkCurvature(.16)
          .linkDirectionalArrowLength(3).linkDirectionalArrowRelPos(.78)
          .linkPositionUpdate((_object,{start,end},link)=>{
            // Native curve is calculated before this callback. Straight fallback supports other library versions.
            const native=link as unknown as Flight & {__curve?:THREE.Curve<THREE.Vector3>|null};
            edgeCurves.set(native.id,native.__curve?.getPoints(40)||[new THREE.Vector3(start.x,start.y,start.z),new THREE.Vector3(end.x,end.y,end.z)]);return false;
          })
          .linkHoverPrecision(8).linkDirectionalParticles(link=>!reduced&&((link as unknown as Flight).id===chosenFlight.current||(link as unknown as Flight).id===hoveredId.current)?3:0).linkDirectionalParticleWidth(2).linkDirectionalParticleSpeed(.004)
          .onNodeClick((_node,event)=>sceneClick(event))
          .onBackgroundClick(event=>sceneClick(event))
          .onLinkClick((_edge,event)=>sceneClick(event));
        function sceneClick(event:MouseEvent){
            // The library's cached hover target can lag a fast pointer-and-click.
            // Resolve the visible sphere at click time before considering an edge or family.
            const bounds=g.renderer().domElement.getBoundingClientRect();
            const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((event.clientX-bounds.left)/bounds.width*2-1,-(event.clientY-bounds.top)/bounds.height*2+1),g.camera());
            let object:THREE.Object3D|null=ray.intersectObjects([...groups.values()].filter(g=>g.visible),true)[0]?.object || null;
            while(object&&!object.userData.datasetId)object=object.parent;
            // In overview the whole constellation is one target, including its empty space.
            if(!focusId.current){
              const hit=ray.intersectObjects(hitRegions,false)[0];
              if(hit){callbacks.current.onGroup?.(hit.object.userData.groupId);return;}
            }
            const node=data.nodes.find(n=>n.id===object?.userData.datasetId);
            if(node){
              if(node.group_id && node.group_id!==focusId.current)callbacks.current.onGroup?.(node.group_id);
              else {
                callbacks.current.onPlanet(node);
              }
              return;
            }
            const id=edgeAt(event),edge=data.edges.find(e=>e.id===id);
            if(edge){callbacks.current.onFlight(edge);return;}

        }
        g.renderer().setPixelRatio(Math.min(window.devicePixelRatio,1.75));
        const sun=new THREE.DirectionalLight('#fff0da',3);sun.position.set(120,100,160);
        g.lights([new THREE.AmbientLight('#bccff0',.45),sun]);
        g.nodeThreeObject(obj=>{
          const n=obj as unknown as Planet;const visual=createPlanetVisual(n,data.nodes.length>32);
          visual.group.userData.datasetId=n.id;
          resources.push(...visual.resources);groups.set(n.id,visual.group);visuals.set(n.id,visual);return visual.group;
        });
        // Camera-centered sky has no box boundary when the user zooms out.
        const {stars,material:starMaterial,resources:starResources}=createStarField();
        g.scene().add(stars);resources.push(...starResources);
        const nodes=positionPlanets(data);g.graphData({nodes,links:data.edges.map(e=>({...e}))});
        const families=data.groups?.length ? data.groups : [{id:'focused',name:data.source_name,sheet:data.sheet,bucket:''}];
        for(const [familyIndex,family] of families.entries()) {
          const members=data.groups?.length ? nodes.filter(n=>n.group_id===family.id) : nodes;if(!members.length)continue;
          const cx=(Math.min(...members.map(n=>n.x))+Math.max(...members.map(n=>n.x)))/2;
          const cy=(Math.min(...members.map(n=>n.y))+Math.max(...members.map(n=>n.y)))/2;
          const radius=Math.max(95,...members.map(n=>Math.hypot(n.x-cx,n.y-cy)+55));

          const diskGeo=new THREE.SphereGeometry(radius,24,16);const diskMat=new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false,side:THREE.DoubleSide});
          const disk=new THREE.Mesh(diskGeo,diskMat);disk.position.set(cx,cy,0);disk.userData.groupId=family.id;g.scene().add(disk);hitRegions.push(disk);resources.push(diskGeo,diskMat);
          const cloud=createConstellationCloud(members,{x:cx,y:cy,z:0},radius,77+familyIndex*17,
            Math.min(1800,Math.floor(7000/families.length)),familyIndex);
          g.scene().add(cloud.group);resources.push(...cloud.resources);
          anchors.set(family.id,new THREE.Vector3(cx,cy+radius+22,0));
        }

        const camera=g.camera() as THREE.PerspectiveCamera;
        const controls=g.controls() as OrbitControls;
        const framing=(members=nodes)=>{
          // Reserve the floating navigation/header area without boxing in the scene.
          const height=el.clientHeight,usable=Math.max(180,height-(el.clientWidth<760?240:190));
          const effectiveFov=2*Math.atan(Math.tan(camera.fov*Math.PI/360)*usable/height)*180/Math.PI;
          const frame=cameraFrame(members,Math.max(.2,(el.clientWidth-80)/usable),effectiveFov);
          frame.y+=frame.distance*Math.tan(camera.fov*Math.PI/360)*.19;
          return frame;
        };
        const syncSky=()=>{stars.position.copy(camera.position);anchors.forEach((anchor,id)=>{
          const label=labelElements.current.get(id);if(!label)return;
          const p=anchor.clone().project(camera);label.style.visibility=p.z<1&&p.z>-1?'visible':'hidden';
          label.style.transform=`translate(-50%,-100%) translate(${(p.x+1)*el.clientWidth/2}px,${(-p.y+1)*el.clientHeight/2}px)`;
        });};
        const configure=()=>{
          const frame=framing();controls.minDistance=frame.minDistance;controls.maxDistance=frame.maxDistance;
          controls.zoomSpeed=1.45;controls.rotateSpeed=.65;controls.enableDamping=true;controls.dampingFactor=.09;controls.enablePan=false;
          const skyRadius=Math.max(8000,frame.maxDistance*4);stars.scale.setScalar(skyRadius);
          camera.far=skyRadius*2;camera.updateProjectionMatrix();syncSky();return frame;
        };
        const fit=(duration:number)=>{const frame=configure();g.cameraPosition({x:frame.x,y:frame.y,z:frame.distance},{x:frame.x,y:frame.y,z:0},duration);};
        let previousView:{position:THREE.Vector3;target:THREE.Vector3}|null=null;
        previewCamera.current=(id,instant=false)=>{
          g.linkVisibility(!id);
          if(id){
            const n=nodes.find(n=>n.id===id);if(!n)return;
            if(!previousView)previousView={position:camera.position.clone(),target:controls.target.clone()};
            const distance=Math.max(controls.minDistance,Math.min(560,el.clientHeight*.8,controls.maxDistance));
            const offset=el.clientWidth>=1000?distance*Math.tan(camera.fov*Math.PI/360)*(el.clientWidth/el.clientHeight)*.69:0;
            const target={x:n.x+offset,y:n.y,z:n.z};g.cameraPosition({x:target.x,y:target.y,z:target.z+distance},target,reduced||instant?0:600);
          }else if(previousView){g.cameraPosition(previousView.position,previousView.target,reduced?0:550);previousView=null;}
        };
        let overviewView:{position:THREE.Vector3;target:THREE.Vector3}|null=null;
        focusCamera.current=(id)=>{
          previousView=null;
          if(!id){
            if(overviewView){g.cameraPosition(overviewView.position,overviewView.target,reduced?0:850);overviewView=null;}
            else fit(reduced?0:850);
            return;
          }
          const members=nodes.filter(n=>n.group_id===id);if(!members.length)return;
          if(!overviewView)overviewView={position:camera.position.clone(),target:controls.target.clone()};
          const frame=framing(members);
          // Move within this scene. Never rebuild, recenter planets or reseed the dust.
          const direction=camera.position.clone().sub(controls.target).normalize();
          const target=new THREE.Vector3(frame.x,frame.y,0);
          g.cameraPosition(target.clone().addScaledVector(direction,frame.distance),target,reduced?0:950);
        };
        resetView.current=()=>fit(reduced?0:550);
        controls.addEventListener('change',syncSky);fit(0);
        if(focusId.current)focusCamera.current(focusId.current);
        if(previewing.current)previewCamera.current(previewing.current);
        edgeAt=(event:MouseEvent|PointerEvent)=>{
          if(previewing.current||!focusId.current)return null;
          const bounds=el.getBoundingClientRect(), point={x:event.clientX-bounds.left,y:event.clientY-bounds.top};
          for(const n of nodes){
            const local=new THREE.Vector3(n.x,n.y,n.z).applyMatrix4(camera.matrixWorldInverse);if(local.z>=0)continue;
            const projected=new THREE.Vector3(n.x,n.y,n.z).project(camera);if(projected.z < -1 || projected.z > 1)continue;
            const x=(projected.x+1)*el.clientWidth/2,y=(1-projected.y)*el.clientHeight/2;
            const radius=(n.parent_id?22:26)*el.clientHeight/(2*Math.tan(camera.fov*Math.PI/360)*-local.z)+5;
            if(Math.hypot(point.x-x,point.y-y)<radius)return null;
          }
          const paths=[...edgeCurves].map(([id,points])=>({id,points:points.map(p=>{const v=p.clone().project(camera);return v.z>=-1&&v.z<=1?{x:(v.x+1)*el.clientWidth/2,y:(1-v.y)*el.clientHeight/2}:{x:NaN,y:NaN};})}));
          return nearestProjectedEdge(point,paths,16);
        };
        const clearHover=()=>{if(hoveredId.current){hoveredId.current=null;g.linkWidth(g.linkWidth()).linkDirectionalParticles(g.linkDirectionalParticles());}setHovered(null);el.style.cursor='grab';};
        const pointerDown=()=>clearHover();
        const pointerMove=(event:PointerEvent)=>{
          if(event.buttons){clearHover();return;}
          const bounds=g.renderer().domElement.getBoundingClientRect();
          const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((event.clientX-bounds.left)/bounds.width*2-1,-(event.clientY-bounds.top)/bounds.height*2+1),camera);
          if(focusId.current&&!previewing.current){
            // The surface alone owns hover. Glow, rings and mist are deliberately inert.
            const surfaces=[...visuals.values()].filter(v=>v.group.visible).map(v=>v.surface);
            let object:THREE.Object3D|null=ray.intersectObjects(surfaces,false)[0]?.object||null;
            while(object&&!object.userData.datasetId)object=object.parent;
            if(object){clearHover();el.style.cursor='pointer';return;}
          }
          const id=edgeAt(event),edge=data.edges.find(e=>e.id===id);if(!edge){clearHover();if(!focusId.current && ray.intersectObjects(hitRegions,false).length)el.style.cursor='pointer';return;}
          if(hoveredId.current!==id){hoveredId.current=id;g.linkWidth(g.linkWidth()).linkDirectionalParticles(g.linkDirectionalParticles());}
          const paneBounds=el.getBoundingClientRect();setHovered({edge,x:Math.max(12,Math.min(el.clientWidth-280,event.clientX-paneBounds.left+18)),y:Math.min(el.clientHeight-140,Math.max(100,event.clientY-paneBounds.top+16))});el.style.cursor='pointer';
        };
        el.addEventListener('pointerdown',pointerDown,true);el.addEventListener('pointermove',pointerMove);el.addEventListener('pointerleave',clearHover);
        let lastWidth=el.clientWidth,lastHeight=el.clientHeight;
        const resize=new ResizeObserver(()=>{if(el.clientWidth && el.clientHeight && (el.clientWidth!==lastWidth || el.clientHeight!==lastHeight)){lastWidth=el.clientWidth;lastHeight=el.clientHeight;g.width(lastWidth).height(lastHeight);if(previewing.current){configure();previewCamera.current(previewing.current,true);}else if(focusId.current)focusCamera.current(focusId.current);else fit(0);}});resize.observe(el);
        const visibility=()=>{
          if(document.hidden){
            g.pauseAnimation();
          }else g.resumeAnimation();
        };document.addEventListener('visibilitychange',visibility);
        const contextLost=(e:Event)=>{e.preventDefault();setError('The 3D view is unavailable. Open Search to browse your files.');g.pauseAnimation();};g.renderer().domElement.addEventListener('webglcontextlost',contextLost);
        let lastFrame=performance.now(),elapsed=0;
        const tick=()=>{
          if(disposed)return;
          const now=performance.now(),delta=Math.max(0,(now-lastFrame)/1000);lastFrame=now;
          if(!document.hidden){
            if(!reduced)elapsed+=Math.min(.05,delta);
            starMaterial.uniforms.time.value=elapsed;syncSky();
            visuals.forEach((visual,id)=>{
              visual.group.visible=!previewing.current||previewing.current===id;
              visual.update(delta,reduced);
            });
          }
          raf=requestAnimationFrame(tick);
        };tick();
        stop=()=>{el.removeEventListener('pointerdown',pointerDown,true);el.removeEventListener('pointermove',pointerMove);el.removeEventListener('pointerleave',clearHover);previewCamera.current=()=>{};focusCamera.current=()=>{};cancelAnimationFrame(raf);controls.removeEventListener('change',syncSky);resetView.current=()=>{};resize.disconnect();document.removeEventListener('visibilitychange',visibility);g.renderer().domElement.removeEventListener('webglcontextlost',contextLost);g._destructor();resources.forEach(r=>r.dispose());el.replaceChildren();graph.current=null;};
        setReady(true);
      }catch {resources.forEach(r=>r.dispose());graph.current?._destructor();graph.current=null;el.replaceChildren();setError('Your browser cannot display the 3D view. Open Search to browse your files.');}
    }).catch(()=>{if(!disposed)setError('Could not load the star map. Open Search to browse your files.');});
    return()=>{disposed=true;stop();};
  },[data,active,reduced]);
  return <div className="planet-scene"><div className="planet-canvas" ref={mount} aria-label="Interactive version star map" role="img" />
    {!focused&&<div className="constellation-labels">{data.groups?.map(family=><button key={family.id} ref={el=>{if(el)labelElements.current.set(family.id,el);else labelElements.current.delete(family.id);}} title={family.name} onClick={()=>{const member=data.nodes.find(n=>n.group_id===family.id&&n.available)||data.nodes.find(n=>n.group_id===family.id);if(member)onGroup?.(family.id);}}>{family.name.split('/').pop()}</button>)}</div>}
    {hovered&&!previewId&&<div className="edge-hover-card" role="tooltip" style={{left:hovered.x,top:hovered.y}}><strong>{hovered.edge.label}</strong>{hovered.edge.columns.length>0&&<span>{hovered.edge.columns.join(', ')}</span>}{hovered.edge.changed_rows!=null&&<span>{hovered.edge.changed_rows.toLocaleString()} rows changed</span>}<small>Click for details</small></div>}
    {!ready&&!error&&<p className="galaxy-loading" role="status">Mapping your versions…</p>}
    {error&&<p className="galaxy-loading" role="status">{error}</p>}
    <div className="galaxy-camera"><button type="button" disabled={!ready} onClick={()=>{if(focused)onReset?.();else resetView.current();}}>Reset</button></div>

  </div>;
}
