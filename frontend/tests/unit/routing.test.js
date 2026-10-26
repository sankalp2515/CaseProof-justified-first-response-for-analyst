import {it,expect} from 'vitest';
import {studioRedirect} from '../../routing.mjs';
it('routes issued customer capabilities to the redesigned reply without modifying them',()=>{
 expect(studioRedirect('/customer/issued_A-b')).toBe('/app/#/victim/reply/issued_A-b');
 expect(studioRedirect('/v1/customer/issued_A-b')).toBeNull();
 expect(studioRedirect('/customer/../internal')).toBeNull();
 expect(studioRedirect('/')).toBeNull();
});
