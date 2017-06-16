#!/usr/bin/env python

"""

Copyright [1999-2016] EMBL-European Bioinformatics Institute

Licensed under the Apache License, Version 2.0 (the "License")
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

		 http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

"""

	Please email comments or questions to the public Ensembl
	developers list at <http://lists.ensembl.org/mailman/listinfo/dev>.

	Questions may also be sent to the Ensembl help desk at
	<http://www.ensembl.org/Help/Contact>.

"""

def compute_z_score_from_pvalue_and_sign(pvalue, sign):

	from scipy.stats import norm
	
	if sign is None:
		return None

	# norm.ppf means:
	# Percent point function (inverse of cdf) at q of the given RV.
	#
	# See:
	# https://docs.scipy.org/doc/scipy-0.14.0/reference/stats.html
	
	z_score = - norm.ppf(pvalue/2) * sign
	
	return z_score

def sign(value):
	if value>0:
		return 1
	
	# None<0 is true, so must test for that separately.
	if value is not None and value<0:
		return -1
	
	if value==0:
		return 0

	raise Exception

def compute_z_score_sign(odds_ratio, beta_coefficient):
	'''
		where the gwas_sign comes from

		beta > 0 gwas_sign = +1
		beta < 0 gwas_sign = -1

		or > 1 gwas_sign = +1
		or < 1 gwas_sign = -1
	'''
	
	if beta_coefficient>0:
		return 1
	
	# None<0 is true, so must test for that separately.
	if beta_coefficient is not None and beta_coefficient<0:
		return -1
	
	if odds_ratio>0:
		return 1
	
	# None<0 is true, so must test for that separately.
	if odds_ratio is not None and odds_ratio<0:
		return -1
	
	return None;

def compute_z_score_from_pvalue_and_odds_ratio_or_beta_coefficient(pvalue, odds_ratio=None, beta_coefficient=None):
	
	return compute_z_score_from_pvalue_and_sign(
		pvalue,
		compute_z_score_sign(odds_ratio, beta_coefficient)
	)

def compute_z_score_for_gwas_snp(gwas_snp):
	
	return compute_z_score_from_pvalue_and_odds_ratio_or_beta_coefficient(
		pvalue           = gwas_snp.pvalue,
		odds_ratio       = gwas_snp.odds_ratio,
		beta_coefficient = gwas_snp.beta_coefficient,
	)

