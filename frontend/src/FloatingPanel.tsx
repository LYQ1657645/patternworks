import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

// Native modal gives keyboard focus containment, Escape and focus restoration.
export default function FloatingPanel({open,onClose,label,children,inline=false,className=''}:{open:boolean;onClose:()=>void;label:string;children:ReactNode;inline?:boolean;className?:string}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    const dialog=ref.current;if(!dialog||inline)return;
    if(open&&!dialog.open)dialog.showModal();else if(!open&&dialog.open)dialog.close();
    return()=>{if(dialog.open)dialog.close();};
  },[open,inline]);
  if(inline)return <>{children}</>;
  return <dialog ref={ref} className={`floating-panel ${className}`} aria-label={label} onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();}}}>{children}</dialog>;
}
