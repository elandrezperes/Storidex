"""Regresiones metodológicas: contrato, revisión, versiones y presupuesto."""
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import audience, contracts, llm, local
from core.phases import p2_persona
from tests.test_sites import api  # noqa: F401


def brief():
    return json.loads(Path('examples/caso_02_producto.json').read_text())


def test_persona_siempre_tiene_dos_llamadas_auditadas(tmp_path):
    with llm.auditar(tmp_path):
        result = p2_persona.ejecutar(brief(), local.research(brief()))
    trace = json.loads((tmp_path / 'trace.json').read_text())
    assert [call['prompt'] for call in trace['llamadas']] == [
        'v2_persona.md', 'v1_autocritica_persona.md']
    assert len(result['afirmaciones']) == 12


def test_edad_se_rechaza_y_se_reintenta_sin_recortarla(monkeypatch, tmp_path):
    valid = local.persona(brief())
    invalid = deepcopy(valid)
    invalid['perfil']['edad'] = 69
    answers, calls = iter([invalid, valid, valid]), []
    def call(system, user, **kwargs):
        calls.append(user)
        return llm.Respuesta(json.dumps(next(answers)), 'fixture')
    monkeypatch.setattr(llm, 'pedir_json', call)
    with llm.auditar(tmp_path):
        assert p2_persona.ejecutar(brief(), {})['perfil']['edad'] == valid['perfil']['edad']
    assert len(calls) == 3
    assert '69' in calls[1] and 'fuera del rango' in calls[1]


def test_prosa_no_se_rescata_y_error_persistido(monkeypatch, tmp_path):
    calls = []
    def call(*args, **kwargs):
        calls.append(1)
        return llm.Respuesta(llm._json_limpio('Aquí tienes: {"ok":true}'), 'fixture')
    monkeypatch.setattr(llm, 'pedir_json', call)
    with llm.auditar(tmp_path), pytest.raises(llm.RespuestaInvalida):
        llm.pedir_validado(llm.Prompt('fixture', 'fixture.md'), '', lambda data: None)
    assert len(calls) == 2
    assert json.loads((tmp_path / 'errors.json').read_text())[0]['fase'] == 'fixture.md'


def test_autocritica_no_silencia_fallo(monkeypatch, tmp_path):
    def call(system, user, **kwargs):
        data = local.persona(brief()) if system.version == 'v2_persona.md' else {}
        return llm.Respuesta(json.dumps(data), 'fixture')
    monkeypatch.setattr(llm, 'pedir_json', call)
    with llm.auditar(tmp_path), pytest.raises(contracts.ContratoInvalido):
        p2_persona.ejecutar(brief(), {})
    assert (tmp_path / 'errors.json').exists()


def test_audiencia_editable_versionada_y_congelada(api):
    project = api(data=brief())
    path = '/' + project['id']
    api(path + '/investigar', {})
    current = api(path + '/persona', {})
    assert current['audiencia']['cobertura']['score'] == 0
    changed = api(path + '/audiencia', {'version': 1, 'campos': {
        'conflicto.objecion': 'Yo quiero conocer el precio antes de ir.'}})
    assert changed['audiencia']['version'] == 2
    claim = changed['audiencia']['afirmaciones']['conflicto.objecion']
    assert claim['nivel'] == 'T1' and claim['veracidad'] == 'sin_verificacion'
    api(path + '/audiencia', {'version': 1, 'campos': {}}, expected=409)
    api(path + '/audiencia', {'version': 2, 'campos': {'perfil.edad': 99}}, expected=400)
    api(path + '/premisas', {'frase': changed['frases'][0]})
    api(path + '/audiencia', {'version': 3, 'campos': {}}, expected=409)
    import sites_backend
    directory = sites_backend._root() / 'usuarios' / ('a'*64) / project['id']
    assert json.loads((directory / 'persona_v1.json').read_text())['version'] == 1
    assert json.loads((directory / 'persona_v3.json').read_text())['version'] == 3
    assert 'conflicto.objecion' in json.loads((directory / 'persona_diff_v2.json').read_text())['campos']


def test_presupuesto_impide_llamada_antes_de_consumir(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, 'MAX_COST', 0.00001)
    monkeypatch.setattr(llm, '_cliente', lambda: SimpleNamespace())
    with llm.auditar(tmp_path), pytest.raises(llm.CosteExcedido):
        llm._pedir_openai('sistema', 'usuario', 'gpt-4o', 0.3)
    assert not (tmp_path / 'trace.json').exists()


def test_escaleta_no_acepta_huecos():
    data = {'beats':[
        {'tc_in':'00:00','tc_out':'00:03','funcion':'hook','descripcion':'Abre una caja.','cuarta_pared':'indirecta'},
        {'tc_in':'00:05','tc_out':'00:15','funcion':'cierre','descripcion':'Cierra la caja.','cuarta_pared':'indirecta'}]}
    with pytest.raises(contracts.ContratoInvalido, match='contiguos'):
        contracts.escaleta(data)


def test_piloto_compara_baseline_aunque_miia_no_entregue(tmp_path, monkeypatch):
    from tools import piloto
    original = piloto.call
    def call(path, data=None):
        if path.endswith('/preparar'):
            raise RuntimeError('Fallo controlado de la condición MIIA')
        return original(path, data)
    monkeypatch.setattr(piloto, 'call', call)
    monkeypatch.setenv('STORIDEX_PROXY_SECRET', 'fixture')
    monkeypatch.setenv('STORIDEX_RUNS_DIR', str(tmp_path / 'runs'))
    args = SimpleNamespace(live=False, sin_busqueda=True, output=str(tmp_path / 'piloto'),
                           case=['caso_02_producto'])
    assert piloto.run(args) == 1
    results = json.loads((tmp_path / 'piloto/resultados.json').read_text())
    assert len(results) == 2 and not results[0]['entregado'] and results[1]['entregado']
    frozen = json.loads((tmp_path / 'piloto/caso_02_producto/baseline/entrada_congelada.json').read_text())
    assert frozen['brief']['marca'] == brief()['marca']
    assert frozen['research']['competencia']['sin_datos']
