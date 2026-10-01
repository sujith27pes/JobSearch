import * as DialogPrimitive from '@radix-ui/react-dialog';
import {X} from 'lucide-react';
import type {ReactNode} from 'react';
export function Modal({open,onClose,title,description,children,wide=false,drawer=false}:{open:boolean;onClose:()=>void;title:string;description?:string;children:ReactNode;wide?:boolean;drawer?:boolean}){
return <DialogPrimitive.Root open={open} onOpenChange={v=>!v&&onClose()}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="overlay"/><DialogPrimitive.Content className={`modal ${wide?'modal-wide':''} ${drawer?'drawer':''}`}><div className="modal-heading"><div><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Description>{description||'Review the information below.'}</DialogPrimitive.Description></div><DialogPrimitive.Close className="icon-button" aria-label="Close"><X size={20}/></DialogPrimitive.Close></div>{children}</DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>}
