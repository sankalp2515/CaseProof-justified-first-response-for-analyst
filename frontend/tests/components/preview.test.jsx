import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
vi.mock('../../src/state/resources.jsx',async original=>({...await original(),useSession:()=>({persona:'reviewer'}),useResource:()=>({data:[],reload:vi.fn()})}));
import Review from '../../src/pages/case/LiveReview.jsx';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('loads the server report preview without treating it as approval',async()=>{
 const fetcher=vi.fn(async()=>new Response(JSON.stringify({revision:7,digest:'server-digest',requires_approval:true,ledger_debits:[{txn_id:'T1',resolved_fields:{amount:5400000}}],unreported:[],evidence_only_debits:[]})));vi.stubGlobal('fetch',fetcher);
 render(<Review view={{snapshot:{case_id:'CASE-A',revision:7,digest:'server-digest',readiness:{satisfied_facts:[],blocking_conflicts:[]}},workflow:{readiness:'REVIEW_REQUIRED',urgent_referral:{}},amounts:{confirmed:5400000}}} reload={()=>{}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Inspect draft report'}));
 expect(await screen.findByText('Draft revision 7')).toBeTruthy();
 expect(screen.getByText('Preview only · reviewer approval still required')).toBeTruthy();
 expect(fetcher.mock.calls[0][0]).toBe('/v1/cases/CASE-A/report-preview');
});
