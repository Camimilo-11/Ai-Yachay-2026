import csv
import tempfile
import unittest
from unittest.mock import patch
import os
from pathlib import Path
import numpy as np

from wifi_rti.acquisition import read_records, write_records, observation_records, reconstruct_scan
from wifi_rti.radio import fspl_db, noise_floor_dbm


class AcquisitionTests(unittest.TestCase):
    def test_rss_roundtrip_preserves_link_order(self):
        baseline = np.array([-40., -50., -60.])
        changes = np.array([3., -2., .5])
        pairs = np.array([[0,1],[0,2],[1,2]])
        records = observation_records(baseline, changes, pairs, 'test', 7, 1.25, 2400., np.ones(3,dtype=bool))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'raw.csv'
            write_records(path, records)
            scan, mask = reconstruct_scan(read_records(path), baseline, pairs)
        np.testing.assert_allclose(scan, changes, atol=1e-10)
        self.assertTrue(mask.all())

    def test_missing_is_blank_not_zero(self):
        pairs=np.array([[0,1]])
        rows=observation_records(np.array([-60.]), np.array([2.]), pairs, 'test', 0, 0., 2400., np.array([False]))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.csv'; write_records(p,rows)
            with p.open(newline='',encoding='utf-8') as f: row=next(csv.DictReader(f))
            self.assertEqual(row['signal_strength'],'')
            values,mask=reconstruct_scan(read_records(p),np.array([-60.]),pairs)
        self.assertFalse(mask[0])
        self.assertTrue(np.isnan(values[0]))

    def test_duplicate_links_rejected(self):
        pairs=np.array([[0,1]])
        rows=observation_records(np.array([-60.]),np.array([0.]),pairs,'test',0,0.,2400.,np.array([True]))
        with self.assertRaises(ValueError): reconstruct_scan(rows+rows,np.array([-60.]),pairs)

    def test_wrong_link_identity_rejected(self):
        pairs=np.array([[0,1]])
        rows=observation_records(np.array([-60.]),np.array([0.]),pairs,'test',0,0.,2400.,np.array([True]))
        rows[0]['tx_id']='node_99'
        with self.assertRaises(ValueError): reconstruct_scan(rows,np.array([-60.]),pairs)

    def test_truth_is_not_in_measurement_record(self):
        rows=observation_records(np.array([-60.]),np.array([0.]),np.array([[0,1]]),'test',0,0.,2400.,np.array([True]))
        self.assertNotIn('x_true_m',rows[0])
        self.assertEqual(rows[0]['source'],'simulation')


class RadioTests(unittest.TestCase):
    def test_frequency_loss_difference(self):
        self.assertAlmostEqual(float(fspl_db(10.,5000.)-fspl_db(10.,2400.)),20*np.log10(5/2.4),places=10)

    def test_doubling_distance_adds_six_db(self):
        self.assertAlmostEqual(float(fspl_db(20.,2400.)-fspl_db(10.,2400.)),20*np.log10(2),places=10)

    def test_invalid_radio_inputs_rejected(self):
        for distance,frequency in [(0,2400),(10,-1),(float('nan'),2400)]:
            with self.assertRaises(ValueError): fspl_db(distance,frequency)

    def test_bandwidth_noise_increment(self):
        self.assertAlmostEqual(noise_floor_dbm(40,7)-noise_floor_dbm(20,7),10*np.log10(2),places=10)


class IntegrationTests(unittest.TestCase):
    def test_csv_corruption_is_detected_after_readback(self):
        from wifi_rti.experiment import Config, run_experiment
        from wifi_rti.acquisition import write_records as original_writer
        def corrupt(path,rows):
            changed=[dict(row) for row in rows]
            for row in changed:
                if row['valid']:row['signal_strength']+=1.
            original_writer(path,changed)
        with tempfile.TemporaryDirectory() as d, patch('wifi_rti.synthetic.write_records',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'CSV'):
                run_experiment(Config(nodes=4,grid_size=4),Path(d))

    def test_quantization_is_separate_from_serialization(self):
        from wifi_rti.experiment import Config, run_experiment
        with tempfile.TemporaryDirectory() as d:
            result=run_experiment(Config(nodes=4,grid_size=4,quantization_db=2.,development_frames=8,test_frames=8),Path(d))
            self.assertLess(result['roundtrip_max_error_db'],1e-10)
            self.assertGreater(result['quantization_max_error_db'],.5)

    def test_no_development_selection_stops_test_evaluation(self):
        from wifi_rti.experiment import Config, run_experiment
        with tempfile.TemporaryDirectory() as d:
            c=Config(nodes=4,grid_size=4,reference_frames=20,calibration_frames=20,noise_validation_frames=5,
                     fingerprints_per_position=3,development_frames=1,test_frames=30,loss_rate=.8)
            result=run_experiment(c,Path(d))
            self.assertEqual(result['status'],'insufficient_development')
            self.assertNotIn('metrics',result)

    def test_source_provenance_independent_of_cwd(self):
        from wifi_rti.experiment import Config, run_experiment
        old=Path.cwd()
        with tempfile.TemporaryDirectory() as d:
            try:
                os.chdir(d)
                result=run_experiment(Config(nodes=4,grid_size=4,development_frames=8,test_frames=8),Path(d)/'out')
            finally:os.chdir(old)
        self.assertIn('em.cpp',result['provenance']['source_sha256'])
        self.assertIn('em_cpp.py',result['provenance']['source_sha256'])

    def test_nonconvergence_is_explicit(self):
        from wifi_rti.experiment import Config, run_experiment
        with tempfile.TemporaryDirectory() as d, patch('wifi_rti.experiment.fit_zero_mean_gmm_em',return_value=(.5,1.,3.,600,False)):
            result=run_experiment(Config(nodes=4,grid_size=4,development_frames=8,test_frames=8),Path(d))
            self.assertEqual(result['status'],'em_not_converged')

    def test_equivalent_maps_use_stable_tie_break(self):
        from wifi_rti.synthetic import Config
        from wifi_rti.evaluation import Evaluator
        from simulacion_rti_em_knn import perimeter_nodes,grid_centers,make_links,elliptical_weights
        c=Config(nodes=4,grid_size=4)
        nodes=perimeter_nodes(4,c.room_m);pairs,a,b=make_links(nodes);pixels=grid_centers(4,c.room_m)
        weights=elliptical_weights(a,b,pixels,c.ellipse_width_m)
        e=Evaluator(c,weights,pixels,np.zeros((len(pixels),len(pairs))),pixels,.42)
        query=np.arange(1,7)*.1
        left,_=e.predict(query,'RTI_EM_Fisher',.1)
        right,_=e.predict(query,'Tikhonov_equivalente_Fisher',.1)
        np.testing.assert_array_equal(left,right)

    def test_invalid_config_rejected(self):
        from wifi_rti.experiment import Config
        for kwargs in [{'rho':1.0},{'loss_rate':-1},{'quantization_db':-1},{'carrier_mhz':float('nan')}]:
            with self.assertRaises(ValueError): Config(**kwargs).validate()

    def test_end_to_end_cpp_features_and_serialization(self):
        from wifi_rti.experiment import Config, run_experiment
        with tempfile.TemporaryDirectory() as d:
            c=Config(nodes=4,grid_size=4,reference_frames=25,calibration_frames=35,fingerprints_per_position=3,development_frames=12,test_frames=15,export_upstream_features=True)
            result=run_experiment(c,Path(d))
            self.assertEqual(result['em']['backend'],'C++17')
            self.assertLess(result['roundtrip_max_error_db'],1e-10)
            self.assertGreater(result['upstream_feature_rows'],0)
            self.assertEqual(result['evaluation_protocol'],'matched_grid')
            self.assertEqual(result['test_frames'],15)
            self.assertIn('Centro_constante',result['metrics'])
            self.assertLess(result['fisher_matched_max_abs_error'],1e-8)

    def test_all_links_lost_does_not_report_localization_success(self):
        from wifi_rti.experiment import Config, run_experiment
        with tempfile.TemporaryDirectory() as d:
            c=Config(nodes=4,grid_size=4,reference_frames=25,calibration_frames=35,fingerprints_per_position=2,development_frames=8,test_frames=8,extra_loss_db=200)
            result=run_experiment(c,Path(d))
            self.assertEqual(result['status'],'insufficient_calibration')
            self.assertNotIn('metrics',result)


if __name__=='__main__': unittest.main()

