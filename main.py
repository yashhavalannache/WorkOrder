from Bio.Seq import Seq
protein_seq = Seq("AGCTTAGCTAGCTACGATCG")
print(protein_seq)
dna_seq = protein_seq.back_transcribe()
print(dna_seq)


