-- NOT executed locally. Official syntax: https://docs.cloud.google.com/bigquery/docs/graph-create
-- Create typed node/edge tables from the local graph export first.
CREATE OR REPLACE PROPERTY GRAPH caseproof.MoneyTrail
 NODE TABLES (caseproof.Accounts KEY(id) LABEL Account,
              caseproof.Identifiers KEY(entity,kind,value) LABEL Identifier)
 EDGE TABLES (
  caseproof.Transfers KEY(txn_id)
   SOURCE KEY(from_account) REFERENCES Accounts(id)
   DESTINATION KEY(to_account) REFERENCES Accounts(id) LABEL Transfer,
  caseproof.AccountIdentifiers KEY(entity,kind,value)
   SOURCE KEY(entity) REFERENCES Accounts(id)
   DESTINATION KEY(entity,kind,value) REFERENCES Identifiers(entity,kind,value)
   LABEL HasIdentifier
 );
-- Victim paths (temporal ordering is also enforced by the application replay).
GRAPH caseproof.MoneyTrail
 MATCH p = (v:Account {id: @victim})-[:Transfer]->{1,3}(a:Account)
 RETURN TO_JSON(p) AS victim_path;
-- Shared caller identifier.
GRAPH caseproof.MoneyTrail
 MATCH (a:Account)-[:HasIdentifier]->(i:Identifier {kind: 'caller_number'})
       <-[:HasIdentifier]-(b:Account)
 WHERE a.id = @victim AND b.id != a.id
 RETURN b.id, i.value;
-- Three-hop neighbours.
GRAPH caseproof.MoneyTrail
 MATCH (a:Account {id: @account})-[:Transfer]-{1,3}(b:Account)
 RETURN DISTINCT b.id;
