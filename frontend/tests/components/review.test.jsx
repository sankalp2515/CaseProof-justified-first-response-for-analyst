import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
const mock=vi.hoisted(()=>({persona:'reviewer',history:[]}));
vi.mock('../../src/state/resources.jsx',async original=>({...await original(),useSession:()=>({persona:mock.persona}),useResource:()=>({data:mock.history,reload:vi.fn()})}));
import Review from '../../src/pages/case/LiveReview.jsx';
const makeView=(revision=1)=>({snapshot:{case_id:'CASE-A',revision,digest:'digest-'+revision,readiness:{policy_version:'demo-v2',satisfied_facts:['bank_verified'],blocking_conflicts:[]}},workflow:{readiness:'REVIEW_REQUIRED',unresolved:['deception_account'],job:null,urgent_referral:{eligible:true,reason:'Confirmed own-bank debit',transaction_ids:['T1']}},amounts:{confirmed:500000}});
afterEach(()=>{cleanup();mock.persona='reviewer';mock.history=[];});
it('recovers an unsent current urgent approval from persisted history',()=>{
 mock.history=[{approval:{approval_id:'URG-A',revision:1,digest:'digest-1',reason:'Supported'},delivery:null}];
 render(<Review view={makeView()} reload={()=>{}}/>);
 expect(screen.getByRole('button',{name:'Send approved referral to simulator'}).disabled).toBe(false);
});
it('does not offer historical urgent approval as a current send',()=>{
 mock.history=[{approval:{approval_id:'URG-A',revision:1,digest:'digest-1',reason:'Supported'},delivery:null}];
 render(<Review view={makeView(2)} reload={()=>{}}/>);
 expect(screen.queryByRole('button',{name:'Send approved referral to simulator'})).toBeNull();
});
it('blocks approval when the current assessment changes while the dialog is open',()=>{
 const {rerender}=render(<Review view={makeView()} reload={()=>{}}/>);
 fireEvent.change(screen.getByLabelText('Reviewer rationale'),{target:{value:'Reviewed bank debit and evidence limitations'}});
 fireEvent.click(screen.getByRole('button',{name:'Review urgent referral'}));
 expect(screen.getByRole('button',{name:'Approve revision 1'}).disabled).toBe(false);
 rerender(<Review view={makeView(2)} reload={()=>{}}/>);
 expect(screen.getByRole('button',{name:'Approve revision 1'}).disabled).toBe(true);
 expect(screen.getByLabelText('Reviewer rationale').value).toContain('Reviewed bank debit');
});
it('keeps the analyst from approving a transaction even if it is eligible',()=>{
 mock.persona='analyst';render(<Review view={makeView()} reload={()=>{}}/>);
 fireEvent.change(screen.getByLabelText('Reviewer rationale'),{target:{value:'Reason'}});
 expect(screen.getByRole('button',{name:'Review urgent referral'}).disabled).toBe(true);
});
