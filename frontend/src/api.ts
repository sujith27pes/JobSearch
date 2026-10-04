import type {components} from './api-schema';
export type Criterion=components['schemas']['Criterion'];
export type JobCreate=components['schemas']['JobCreate'];
export async function api<T=any>(path:string,init:RequestInit={}):Promise<T>{
 let response:Response;
 try {response=await fetch('/api'+path,{...init,headers:{...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}),...init.headers}});} catch {throw new Error('JobScore could not reach the server. Check that the application is running, then refresh. Your saved work is retained.');}
 if(!response.ok){const body=await response.json().catch(()=>({detail:response.statusText}));throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));}
 return response.json();
}
export const send=(method:string,body?:unknown):RequestInit=>({method,body:body===undefined?undefined:JSON.stringify(body)});
export type Row=Record<string,any>;
export const sourceLabels:Record<string,string>={current_applicant:'Applicants',past_applicant:'Rediscovered',employee:'Internal talent'};
export const statusLabels:Record<string,string>={supported:'Supported',partial:'Partial',not_evidenced:'Needs clarification',unmet:'Does not meet requirement',not_reviewed:'Not reviewed',reviewing:'Reviewing',shortlisted:'Shortlisted',reviewed_not_shortlisted:'Not shortlisted',rejected:'Reject for this job'};
