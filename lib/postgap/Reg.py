#! /usr/bin/env python

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

import Globals
from postgap.DataModel import *
import postgap.BedTools
from postgap.Utils import *
import logging

class Reg_source(object):
	logger = logging.getLogger(__name__)
	def run(self, ld_snps, tissues):
		"""

			Extract score at sns of interest
			Args:
			* [ SNP ]
			* [ string ]
			Returntype: [ Regulatory_Evidence ]

		"""
		assert False, "This stub should be defined"

class Regulome(Reg_source):
	display_name = "Regulome"
	def run(self, ld_snps, tissues):
		"""

			Extract Regulome score at sns of interest
			Args:
			* [ SNP ]
			* [ string ]
			Returntype: [ Regulatory_Evidence ]

		"""
		snp_hash = dict( (snp.rsID, snp) for snp in ld_snps)
		intersection = postgap.BedTools.overlap_snps_to_bed(ld_snps, postgap.Globals.DATABASES_DIR + "/Regulome.bed")
		res = filter (lambda X: X.score, (self.get_regulome_evidence(feature, snp_hash) for feature in intersection))

		self.logger.info("\tFound %i regulatory variants in Regulome" % (len(res)))

		return res

	def get_regulome_evidence(self, feature, snp_hash):
		"""

			Extract Regulome score from bedtools output
			Args:
			* string
			Returntype: Regulatory_Evidence

		"""

		'''
		First 4 columns are from Regulome file, the next 4 are LD SNP coords
		Regulome file format:
		1. chrom
		2. start
		3. end
		4. category

		LD SNP coords:
		5. chrom
		6. start
		7. end
		8. rsID
		'''
		return Regulatory_Evidence(
				snp = snp_hash[feature[7]],
				source = self.display_name,
				score = 2 if feature[3][0] == '1' or feature[3][0] == '2' else 1,
				study = None,
				tissue = None,
				info = None
			)

class VEP_reg(Reg_source):
	display_name = 'VEP_reg'
	def run(self, snps, tissues):
		"""

			Returns all genes associated to a set of SNPs in VEP
			Args:
			* [ SNP ]
			* [ string ] (tissues)
			Returntype: [ Regulatory_Evidence ]

		"""
		list = concatenate(self.get(chunk) for chunk in chunks(snps, 199))
		'''

			Example output from VEP:
			[
				{
					'colocated_variants': [
						{
							'phenotype_or_disease': 1,
							'seq_region_name': '9',
							'eas_allele': 'C',
							'amr_maf': '0.4553',
							'strand': 1,
							'sas_allele': 'C',
							'id': 'rs1333049',
							'allele_string': 'G/C',
							'sas_maf': '0.4908',
							'amr_allele': 'C',
							'minor_allele_freq': '0.4181',
							'afr_allele': 'C',
							'eas_maf': '0.5367',
							'afr_maf': '0.2133',
							'end': 22125504,
							'eur_maf': '0.4722',
							'eur_allele': 'C',
							'minor_allele': 'C',
							'pubmed': [
								24262325,
							],
							'start': 22125504
						}
					],
					'assembly_name': 'GRCh38',
					'end': 22125504,
					'seq_region_name': '9',
					'transcript_consequences': [
						{
							'gene_id': 'ENSG00000240498',
							'variant_allele': 'C',
							'distance': 4932,
							'biotype': 'antisense',
							'gene_symbol_source': 'HGNC',
							'consequence_terms': [
								'downstream_gene_variant'
							],
							'strand': 1,
							'hgnc_id': 'HGNC:34341',
							'gene_symbol': 'CDKN2B-AS1',
							'transcript_id': 'ENST00000584020',
							'impact': 'MODIFIER'
						},
					],
					'strand': 1,
					'id': 'rs1333049',
					'most_severe_consequence': 'downstream_gene_variant',
					'allele_string': 'G/C',
					'start': 22125504
				}
			]

		'''

		snp_hash = dict( (snp.rsID, snp) for snp in snps)
		res = []
		for hit in list:
			MAFs = None
			for variant in hit['colocated_variants']:
				if variant['id'] == hit['id']:
					 MAFs = variant
					 break

			if MAFs is not None:
				res.append(Regulatory_Evidence(
					snp = snp_hash[hit['input']],
					score = 0,
					source = self.display_name,
					study = None,
					tissue = None,
					info = {
						'MAFs': MAFs
					}
				))

		self.logger.info("\tFound %i interactions in VEP" % (len(res)))

		return res

	def remove_none_elements(self, list):
		return filter(self.exists, list)

	def exists(self, it):
		return (it is not None)

	def get(self, chunk_param):
		"""

			Queries Ensembl servers. Recursively breaks down query if error code 400 is returned
			Args:
			* [ SNP ]
			Returntype: [ Regulatory_Evidence ]

		"""

		# 
		chunk = self.remove_none_elements(chunk_param)

		if len(chunk) == 0:
			return []

		try:
			server = "http://grch37.rest.ensembl.org"
			ext = "/vep/%s/id" % (postgap.Globals.SPECIES)
			return postgap.REST.get(server, ext, data = {"ids" : [snp.rsID for snp in chunk]})

		except requests.exceptions.HTTPError as error:
			if error.response.status_code == 400 or error.response.status_code == 504:
				if len(chunk) == 1:
					return []
				else:
					return self.get(chunk[:len(chunk)/2]) + self.get(chunk[len(chunk)/2:])
			raise

sources = Reg_source.__subclasses__()
