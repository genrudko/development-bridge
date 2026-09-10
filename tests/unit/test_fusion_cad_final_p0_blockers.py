from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.api.errors import ErrorCode
from app.fusion_cad.errors import FusionCadError
from app.fusion_cad.scripts import FusionCadScriptBundle
from app.fusion_cad.transactions import TransactionState, TransactionStore


def _scope():
    s=FusionCadScriptBundle.build('transaction',{'operation':'test_op'}); d={'__name__':'__main__'}
    exec(compile(s,'<p0-final>','exec'),d)  # noqa: S102
    return d

def test_copy_safe_document_identity():
    identity=_scope()['_fusion_document_identity']
    a=SimpleNamespace(dataFile=SimpleNamespace(id='cloud-a'),dataId='legacy-a',creationId='same',savedVersion=7,name='A')
    b=SimpleNamespace(dataFile=SimpleNamespace(id='cloud-b'),dataId='legacy-b',creationId='same',savedVersion=7,name='B')
    assert identity(a)['document_ref']=='doc_cloud-a'
    assert identity(b)['document_ref']=='doc_cloud-b'
    assert identity(a)['identity_source']=='dataFile.id'
    unsaved=SimpleNamespace(dataFile=None,dataId=None,creationId='session-x',savedVersion=None,name='Untitled')
    assert identity(unsaved)['document_ref']=='doc_unsaved_session-x'
    ambiguous=SimpleNamespace(dataFile=None,dataId=None,creationId='same',savedVersion=3,name='Saved')
    with pytest.raises(RuntimeError) as exc: identity(ambiguous)
    assert getattr(exc.value,'code',None)=='NO_ACTIVE_DESIGN'

def test_replay_hash_ignores_native_token_churn_but_tracks_text():
    snap=_scope()['_transaction_snapshot_from_fingerprint']
    base={'document':{'document_ref':'doc_a','name':'Golden'},'timeline':[{'index':0,'id':'t-a','name':'Text'}],'components':[{'id':'c-a','name':'Root'}],'sketches':[{'id':'s-a','name':'Sketch'}],'sketch_texts':[{'id':'x-a','text':'ПЫТОК','font':'Arial','height':0.4}],'attributes':[{'owner_id':'x-a','group':'bridge.cad/v1','name':'provenance','value':json.dumps({'logical_object_ref':'txt_1'})}]}
    churn={**base,'timeline':[{**base['timeline'][0],'id':'t-b'}],'components':[{**base['components'][0],'id':'c-b'}],'sketches':[{**base['sketches'][0],'id':'s-b'}],'sketch_texts':[{**base['sketch_texts'][0],'id':'x-b'}],'attributes':[{**base['attributes'][0],'owner_id':'x-b'}]}
    changed={**churn,'sketch_texts':[{**churn['sketch_texts'][0],'text':'ПЫТОК!'}]}
    assert snap('fp-a',base)['structural_hash']==snap('fp-b',churn)['structural_hash']
    assert snap('fp-a',base)['structural_hash']!=snap('fp-c',changed)['structural_hash']

def test_commit_reservation_blocks_replay_until_terminal_equivalence():
    store=TransactionStore(); store.begin('tx','doc_1','rev_1','fp_1',{})
    staged=store.stage('tx',{'action_type':'text_create'}); sig={'plan_hash':staged.plan_hash,'structural_hash':'a'}
    store.begin_preview('tx','fp_1'); store.finish_preview('tx',preview={'replay_signature':sig})
    assert store.begin_commit('tx','fp_1').state is TransactionState.COMMITTING
    with pytest.raises(FusionCadError): store.begin_commit('tx','fp_1')
    with pytest.raises(FusionCadError): store.stage('tx',{'action_type':'text_create'})
    with pytest.raises(FusionCadError): store.rollback('tx')
    with pytest.raises(FusionCadError) as exc: store.finish_commit('tx',{'replay_signature':{**sig,'structural_hash':'b'},'applied':True})
    assert exc.value.code==ErrorCode.TRANSACTION_CONFLICT
    assert store.get('tx').state is TransactionState.COMMITTING

def test_validation_uses_timeline_entity_and_health_state(monkeypatch):
    import sys
    import types
    scope=_scope(); collect=scope['collect_p0_validation_evidence']
    class C:
        def __init__(self,x=()): self.x=list(x)
        @property
        def count(self): return len(self.x)
        def item(self,i): return self.x[i]
    feature=SimpleNamespace(entityToken='feature-1',name='Broken Extrude',isValid=False,objectType='adsk::fusion::ExtrudeFeature')
    row=SimpleNamespace(index=0,entity=feature,healthState='ErrorFeatureHealthState',isRolledBack=False,errorOrWarningMessage='broken')
    group=SimpleNamespace(index=1,entity=None,healthState='HealthyFeatureHealthState',isRolledBack=False,name='Group')
    design=SimpleNamespace(timeline=C([row,group]),allComponents=C([]),rootComponent=SimpleNamespace())
    class Products:
        def itemByProductType(self,t): return design
    doc=SimpleNamespace(products=Products()); app=SimpleNamespace(activeDocument=doc,activeProduct=design)
    adsk=types.ModuleType('adsk'); core=types.ModuleType('adsk.core'); fusion=types.ModuleType('adsk.fusion')
    core.Application=SimpleNamespace(get=lambda:app); fusion.Design=SimpleNamespace(cast=lambda v:v if v is design else None)
    adsk.core=core; adsk.fusion=fusion
    monkeypatch.setitem(sys.modules,'adsk',adsk); monkeypatch.setitem(sys.modules,'adsk.core',core); monkeypatch.setitem(sys.modules,'adsk.fusion',fusion)
    facts=collect({}, {'bodies':[],'sketches':[]}, 'doc_cloud')
    assert facts['features']==[{'kind':'feature','native_token':'feature-1','name':'Broken Extrude','valid':False,'health':'error'}]
    assert facts['references']==[{'kind':'feature','native_token':'feature-1','state':'broken'}]


def test_proven_not_applied_commit_reservation_can_be_released():
    store=TransactionStore(); store.begin('tx_release','doc_1','rev_1','fp_1',{})
    staged=store.stage('tx_release',{'action_type':'text_create'}); sig={'plan_hash':staged.plan_hash}
    store.begin_preview('tx_release','fp_1'); store.finish_preview('tx_release',preview={'replay_signature':sig})
    store.begin_commit('tx_release','fp_1')
    assert store.release_commit_reservation('tx_release').state is TransactionState.STAGED
    assert store.begin_commit('tx_release','fp_1').state is TransactionState.COMMITTING


def test_authoritative_fingerprint_defines_sketch_text_finite_number_helper():
    from app.fusion_cad.scripts import FusionCadScriptBundle

    source = FusionCadScriptBundle().build("read", {"operation": "model_snapshot"})
    assert "_finite_number(" in source
    assert "def _finite_number(" in source


class _LiveBrokenSketchText:
    def __init__(self):
        self.text = "ПЫТОК"
        self.height = 0.4
        self.fontName = "Rubik"

    @property
    def textParameter(self):
        raise RuntimeError("3 : Parameter is not numeric type")

    @property
    def heightParameter(self):
        raise RuntimeError("3 : Parameter is not text type")


def test_sketch_text_semantics_fall_back_when_live_parameter_getters_raise():
    scope = _scope()
    text = _LiveBrokenSketchText()
    assert scope["_sketch_text_text_value"](text) == "ПЫТОК"
    assert scope["_sketch_text_height_value"](text) == pytest.approx(0.4)
    scope["_sketch_text_set_text_value"](text, "BRIDGE_Ω_ТЕСТ")
    scope["_sketch_text_set_height_value"](text, 0.55)
    assert text.text == "BRIDGE_Ω_ТЕСТ"
    assert text.height == pytest.approx(0.55)


def test_sketch_text_semantics_prefer_parameter_api_when_it_works():
    text_parameter = SimpleNamespace(textValue="ПЫТОК")
    height_parameter = SimpleNamespace(value=0.4)
    text = SimpleNamespace(textParameter=text_parameter, heightParameter=height_parameter, text="legacy-text", height=9.9)
    scope = _scope()
    assert scope["_sketch_text_text_value"](text) == "ПЫТОК"
    assert scope["_sketch_text_height_value"](text) == pytest.approx(0.4)
    scope["_sketch_text_set_text_value"](text, "NEW")
    scope["_sketch_text_set_height_value"](text, 0.5)
    assert text_parameter.textValue == "NEW"
    assert height_parameter.value == pytest.approx(0.5)
    assert text.text == "legacy-text"
    assert text.height == pytest.approx(9.9)
