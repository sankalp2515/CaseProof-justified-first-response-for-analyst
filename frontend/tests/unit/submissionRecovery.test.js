import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import {webcrypto} from 'node:crypto';
vi.mock('../../src/api/client.js',async original=>({...await original(),apiRequest:vi.fn(),post:vi.fn()}));
import {apiRequest,post} from '../../src/api/client.js';
import {prepareJournal,submitReport,readJournal,hashFile} from '../../src/features/victim/submission.js';
function file(name,text){const f=new File([text],name,{type:'text/plain'});f.arrayBuffer=async()=>new TextEncoder().encode(text).buffer;return {file:f,kind:'messages'};}
beforeEach(()=>{sessionStorage.clear();vi.resetAllMocks();vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>vi.unstubAllGlobals());
it('reuses exact submission body after a lost registration response',async()=>{
 const journal=await prepareJournal('A',{narrative:'My original incident account',transaction_ids:[],payment_authorisation:'unsure'},[]);
 post.mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce({case_id:'CASE-A'});
 await expect(submitReport('A',journal,[])).rejects.toThrow('Connection lost');
 expect(readJournal('A').payload).toEqual(journal.payload);
 apiRequest.mockResolvedValue({artifacts:[]});await submitReport('A',readJournal('A'),[]);
 expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);expect(post.mock.calls[0][1].submission_id).toBe(journal.payload.submission_id);
});
it('reconciles an upload that succeeded despite a lost response and retains other failed files',async()=>{
 const files=[file('first.txt','first evidence'),file('second.txt','second evidence')];
 const journal=await prepareJournal('A',{narrative:'A scam incident'},files);post.mockResolvedValue({case_id:'CASE-A'});
 const firstHash=await hashFile(files[0].file);
 apiRequest.mockResolvedValueOnce({artifacts:[]}).mockRejectedValueOnce(new Error('Lost response'))
 .mockResolvedValueOnce({artifacts:[{sha256:firstHash}]}).mockRejectedValueOnce(new Error('Receiver unavailable'))
 .mockResolvedValueOnce({artifacts:[{sha256:firstHash}]});
 const result=await submitReport('A',journal,files);
 expect(result.caseId).toBe('CASE-A');expect(result.files.map(f=>f.state)).toEqual(['received','pending']);
 expect(result.files[1].error).toBe('Receiver unavailable');
 expect(readJournal('A').caseId).toBe('CASE-A');expect(post).toHaveBeenCalledTimes(1);
});
it('asks for file reselection after reload instead of claiming that bytes were restored',async()=>{
 const files=[file('proof.txt','original proof')];const journal=await prepareJournal('A',{narrative:'Incident'},files);
 journal.caseId='CASE-A';apiRequest.mockResolvedValue({artifacts:[]});
 const result=await submitReport('A',journal,[]);
 expect(result.files[0].state).toBe('pending');expect(result.files[0].error).toContain('Reselect');
 expect(apiRequest).toHaveBeenCalledTimes(1);expect(post).not.toHaveBeenCalled();
});
