import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
const mock=vi.hoisted(()=>({release:null}));
vi.mock('../../src/state/resources.jsx',async original=>({...await original(),useSession:()=>({setPersona:vi.fn()}),useResource:()=>({data:{customers:[{account:'OLD',display_name:'Old practice customer'}]},reload:vi.fn()})}));
vi.mock('../../src/api/client.js',async original=>({...await original(),post:vi.fn(async()=>({session_id:'new'})),apiRequest:vi.fn(path=>String(path).includes('/progress')?Promise.resolve({ready:true,published:6,total:6}):new Promise(resolve=>{mock.release=resolve;}))}));
import Victim from '../../src/pages/victim/Victim.jsx';
afterEach(cleanup);
it('keeps old practice accounts disabled until the new catalogue is loaded',async()=>{
 render(<Victim route='/victim/start'/>);
 fireEvent.click(screen.getByRole('button',{name:'Start a fresh practice session'}));
 await waitFor(()=>expect(mock.release).toBeTypeOf('function'));
 expect(screen.getByRole('button',{name:/Old practice customer/}).disabled).toBe(true);
 mock.release({customers:[{account:'NEW',display_name:'New practice customer'}]});
 await waitFor(()=>expect(screen.getByRole('button',{name:/New practice customer/})).toBeTruthy());
 expect(screen.queryByRole('button',{name:/Old practice customer/})).toBeNull();
});
