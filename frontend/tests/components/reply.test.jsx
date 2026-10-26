import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
const mock=vi.hoisted(()=>({data:null}));
vi.mock('../../src/state/resources.jsx',async original=>({...await original(),useSession:()=>({setPersona:vi.fn()}),useResource:()=>({data:mock.data,reload:vi.fn()})}));
vi.mock('../../src/api/client.js',async original=>({...await original(),post:vi.fn(async()=>({received:true}))}));
import Victim from '../../src/pages/victim/Victim.jsx';
afterEach(()=>{cleanup();location.hash='';});
it('allows a server-resolved cloud reply whose envelope has no local can_complete field',()=>{
 mock.data={request:'Clarify the incident',expires_at:9999999999};render(<Victim route='/victim/reply/test-only'/>);
 expect(screen.getByRole('button',{name:'Submit reply',exact:true}).disabled).toBe(false);
});
it('retains the report return target when a consumed capability becomes unavailable',async()=>{
 mock.data={request:'Clarify',case_id:'CASE-A',can_complete:true,expires_at:9999999999};
 const {rerender}=render(<Victim route='/victim/reply/test-only'/>);
 fireEvent.change(screen.getByRole('textbox',{name:'Notes / explanation'}),{target:{value:'Synthetic response'}});
 fireEvent.click(screen.getByRole('button',{name:'Submit reply',exact:true}));
 await screen.findByRole('heading',{name:'Thank you. Your reply is received.'});
 mock.data=null;rerender(<Victim route='/victim/reply/test-only'/>);
 fireEvent.click(screen.getByRole('button',{name:'Return to your report'}));
 await waitFor(()=>expect(location.hash).toBe('#/victim/complaints/CASE-A'));
});
