from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import unittest

from . import rolling_diagnosis as rolling, source_events
from .local_slow_clusters import analyze
from .source_selection import select_sources, render, SelectionOptions
from .test_local_slow_clusters import fork
from .test_source_events import capture, cross_node_capture


def observations(**kwargs):
    rows, edges, coords, preps = capture(**kwargs)
    tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
    return source_events.preparation_sources(preps, rows, edges, coords, tasks, rolling.RollingOptions())


def execution():
    values, edges = fork()
    return analyze(values, edges)


class SourceSelectionTests(unittest.TestCase):
    def test_supported_preparation_wins_without_injection_input_and_preserves_inputs(self):
        resource, hosts = execution(), observations(host_delay=True)
        before = deepcopy((resource, hosts))
        report = select_sources(resource, hosts)
        self.assertEqual(report['selected_mechanism'], 'host_preparation_late')
        self.assertEqual(report['summary']['candidate_count'], 1)
        source = report['candidates'][0]
        self.assertEqual(source['user_rank'], 0)
        self.assertIsNone(source['graph_id'])
        self.assertIsNone(source['stream_id'])
        self.assertIsNone(source['task_id'])
        self.assertEqual(source['anchor_graph_id'], 'i5p1')
        self.assertEqual(report['host_support_chains'][0]['notify_edge_ids'], ['i5e1'])
        self.assertEqual(report['host_support_chains'][0]['support_provenance'], 'original_endpoint_facts')
        self.assertFalse(report['chains'])
        self.assertEqual((resource, hosts), before)
        self.assertEqual(report['execution_proposal'], resource)
        self.assertIn('association, not a graph edge', render(report))

    def test_no_supported_host_keeps_resource_candidates_and_paths_identical(self):
        resource = execution()
        hosts = observations(host_delay=True)
        hosts[0]['status'] = 'unresolved_host_preparation'
        for host_list in ([], hosts):
            report = select_sources(resource, host_list)
            self.assertEqual(report['candidates'], resource['candidates'])
            self.assertEqual(report['chains'], resource['chains'])
            self.assertFalse(report['host_support_chains'])

    def test_normal_preparation_generates_no_host_proposal(self):
        report = select_sources(execution(), observations())
        self.assertFalse([p for p in report['proposals'] if p['mechanism'] == 'host_preparation_late'])

    def test_higher_execution_excess_can_defeat_a_supported_host(self):
        resource = execution()
        for task in resource['candidates']:
            task['duration_ns'] = 1000000
        report = select_sources(resource, observations(host_delay=True))
        self.assertEqual(report['selected_mechanism'], 'communication_execution_growth')

    def test_invalid_or_incomplete_support_never_promoted(self):
        for failure in ('history', 'wrong_rank', 'missing_paths', 'missing_endpoint', 'wait_start',
                        'record_stop', 'api_start', 'duplicate_wait', 'weak_edge', 'duration', 'reference_mean'):
            with self.subTest(failure=failure):
                hosts = observations(host_delay=True)
                host = hosts[0]
                if failure == 'history':
                    host['reference_iterations'][0] = 5
                elif failure == 'wrong_rank':
                    host['reference_preparations'][0]['user_rank'] = 3
                elif failure == 'missing_paths':
                    host['evidence_paths'] = {}
                elif failure == 'missing_endpoint':
                    host['supporting_dependencies'] = []
                elif failure == 'wait_start':
                    host['supporting_dependencies'][0]['wait']['observed_start_ns'] = host['observed_stop_ns']
                elif failure == 'record_stop':
                    host['supporting_dependencies'][0]['producer']['observed_stop_ns'] += 1000000
                elif failure == 'api_start':
                    host['api_start_ns'] = host['observed_start_ns'] - 1
                elif failure == 'duplicate_wait':
                    host['supporting_dependencies'] *= 2
                elif failure == 'weak_edge':
                    host['supporting_dependencies'][0]['edge']['confidence'] = 'semantic'
                elif failure == 'duration':
                    host['duration_ns'] = 10
                elif failure == 'reference_mean':
                    host['reference_mean_ns'] = '0'
                report = select_sources(execution(), hosts)
                self.assertEqual(report['selected_mechanism'], 'communication_execution_growth')
                self.assertEqual(len(report['host_admission_decisions']), 1)

    def test_old_support_is_explicit_and_never_invents_endpoints(self):
        hosts = observations(host_delay=True)
        hosts[0].pop('support_evidence_version')
        hosts[0].pop('supporting_dependencies')
        report = select_sources(execution(), hosts)
        self.assertEqual(report['selected_mechanism'], 'communication_execution_growth')
        report = select_sources(execution(), hosts, allow_inherited_support=True)
        support = report['host_support_chains'][0]
        self.assertEqual(support['support_provenance'], 'sealed_prior_analysis')
        self.assertEqual(support['endpoint_facts'], [])
        self.assertIn('not a reconstructed execution path', render(report))

    def test_new_support_failure_never_falls_back_to_old_claim(self):
        hosts = observations(host_delay=True)
        hosts[0]['supporting_dependencies'] = []
        report = select_sources(execution(), hosts, allow_inherited_support=True)
        self.assertEqual(report['selected_mechanism'], 'communication_execution_growth')

    def test_cross_node_support_needs_existing_clock_margins(self):
        rows, edges, coords, preps, alignment = cross_node_capture()
        tasks = rolling.compare_tasks(rows, edges, coords, rolling.RollingOptions())
        hosts = source_events.preparation_sources(preps, rows, edges, coords, tasks, rolling.RollingOptions(), alignment=alignment)
        self.assertEqual(select_sources(execution(), hosts)['selected_mechanism'], 'host_preparation_late')
        hosts[0]['supporting_dependencies'][0]['alignment']['sender_error_ns'] = 1000000
        self.assertEqual(select_sources(execution(), hosts)['selected_mechanism'], 'communication_execution_growth')

    def test_thresholds_must_match_and_invalid_scores_rejected(self):
        with self.assertRaises(ValueError):
            select_sources(execution(), [], SelectionOptions(source_factor='2'))
        for value in ('NaN', '-1', 'Infinity'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SelectionOptions(mad_multiplier=value).validate()

    def test_duplicate_host_is_rejected_and_no_proposals_is_unlocalized(self):
        hosts = observations(host_delay=True)
        with self.assertRaises(ValueError):
            select_sources(execution(), hosts * 2)
        resource = execution()
        resource['candidates'] = []
        report = select_sources(resource, [])
        self.assertEqual(report['selected_mechanism'], 'unlocalized')
        self.assertIsNone(report['primary_proposal'])

    def test_options_default_is_frozen(self):
        self.assertEqual(asdict(SelectionOptions()), dict(source_factor='1.5', mad_multiplier='3'))


if __name__ == '__main__':
    unittest.main()
