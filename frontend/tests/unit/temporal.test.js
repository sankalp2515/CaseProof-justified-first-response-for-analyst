import {it,expect} from 'vitest';
import {remainingAt} from '../../src/models/caseView.js';
it('interpolates server-clock minutes without rejuvenating on reload',()=>{
 const sample='2026-10-16T12:00:00Z',now=Date.parse(sample)+30000;
 expect(remainingAt({golden_hour_remaining:1.5,as_of:sample},now)).toBe(1);
 expect(remainingAt({golden_hour_remaining:null,as_of:sample},now)).toBe(null);
 expect(remainingAt({golden_hour_remaining:1.5,as_of:sample,replay:true},now)).toBe(1.5);
});
